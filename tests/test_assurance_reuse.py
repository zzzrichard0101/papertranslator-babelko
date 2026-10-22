import copy,json
import pytest
from babelko.assurance import REVISION,fingerprint,tasks,accepted,audit
from babelko.assurance_reuse import AuditMemory,delta_checks,preserve,identity
from babelko.storage import save


def evidence(record,bad=()):
    values=[]
    for item in tasks(record['source'],record['final']):
        other=('t' if item['side']=='source' else 's')+item['id'][1:]
        values.append(dict(id=item['id'],verdict='partial' if item['id'] in bad else 'faithful',evidence=[other],reason='noun omitted' if item['id'] in bad else ''))
    record['assurance']=dict(revision=REVISION,fingerprint=fingerprint(record),checks=values)
    return record


def paragraph():
    source=' '.join(f'Researcher {name} records observations.' for name in ['Sara','Luis','Mei','Hana','Ravi','Nora','Owen','Lina','Evan','Maya','Iris','Noah'])
    target=' '.join(f'{name}는 관찰 내용을 기록한다.' for name in ['Sara','Luis','Mei','Hana','Ravi','Nora','Owen','Lina','Evan','Maya','Iris','Noah'])
    return dict(key='base',source=source,final=target,label='text',context='Methods',neighbors=['Previous passage.','Next passage.'])


def test_format_only_change_reuses_complete_evidence_and_keeps_original(tmp_path):
    old=evidence(dict(key='old',label='text',source="<style id='1'>The study</style> records observations.",final="<style id='1'>연구는</style> 관찰 내용을 기록한다.",context='Methods',neighbors=['The preceding paragraph.']))
    save(tmp_path/'old.json',old);before=copy.deepcopy(old)
    current=dict(key='new',label='text',source='The study records observations.',final='연구는 관찰 내용을 기록한다.',context='Methods',neighbors=['The preceding paragraph.'])
    memory=AuditMemory(tmp_path)
    assert identity(current)==identity(old) and memory.restore(current) and accepted(current)
    assert current['assurance']['checked_now']==0 and current['assurance']['reuse']['from_key']=='old'
    from babelko.storage import read
    assert read(tmp_path/'old.json')==before


@pytest.mark.parametrize('field,value',[
    ('source','The study does not record observations.'),('final','연구는 관찰 내용을 기록하지 않는다.'),
    ('context','Contraindications'),('neighbors',['Changed factual context.']),
    ('formula_hints',{'{v1}':'a different quantity'}),('label','title'),
])
def test_semantic_context_or_text_change_cannot_borrow_approval(tmp_path,field,value):
    old=evidence(dict(key='old',label='text',source='The study records observations.',final='연구는 관찰 내용을 기록한다.',context='Methods',neighbors=[]))
    save(tmp_path/'old.json',old);current=copy.deepcopy(old);current.pop('assurance');current['key']='new';current[field]=value
    assert not AuditMemory(tmp_path).restore(current)


def test_structurally_invalid_tags_cannot_borrow_semantic_approval(tmp_path):
    old=evidence(dict(key='old',label='text',source="<style id='1'>The study</style> records observations.",final="<style id='1'>연구는</style> 관찰 내용을 기록한다.",context=''))
    save(tmp_path/'old.json',old);current=copy.deepcopy(old);current.pop('assurance');current['final']='연구는 관찰 내용을 기록한다.'
    assert not AuditMemory(tmp_path).restore(current)


def test_small_target_repair_rechecks_defect_neighbors_and_dependencies():
    old=paragraph();old['final']=old['final'].replace('Mei는 관찰 내용을 기록한다.','Mei는 문서를 분류한다.');evidence(old,bad=('s2','t2'))
    current=copy.deepcopy(old);preserve(current);current['final']=current['final'].replace('Mei는 문서를 분류한다.','Mei는 관찰 내용을 기록한다.');current.pop('assurance')
    kept=delta_checks(old,current)
    assert kept and not ({'s0','s1','s2','s3','s4','t0','t1','t2','t3','t4'}&set(kept))
    calls=[]
    def request(messages,schema):
        data=json.loads(messages[1]['content']);calls.append(data)
        assert len(data['UNITS'])==24 and 's2' in {x['id'] for x in data['UNITS']}
        assert not any(k in data['CHECK_IDS'] for k in kept)
        return json.dumps([dict(id=x['id'],verdict='faithful',evidence=[('t' if x['side']=='source' else 's')+x['id'][1:]],reason='') for x in data['UNITS'] if x['id'] in data['CHECK_IDS']])
    current['assurance']=audit(current,request)
    assert accepted(current) and current['assurance']['reused_checks']==len(kept)
    assert len(calls)==2 and current['assurance']['checked_now']==10


@pytest.mark.parametrize('change',[
    'negation','condition','quantity','source','context','neighbors','boundary','reorder','placeholder',
])
def test_scope_or_boundary_changes_keep_full_audit(change):
    old=evidence(paragraph());current=copy.deepcopy(old)
    replacements=dict(negation='Mei는 관찰 내용을 기록하지 않는다.',condition='Mei는 허가가 있는 경우 관찰 내용을 기록한다.',quantity='Mei는 24개의 관찰 내용을 기록한다.')
    if change in replacements:current['final']=current['final'].replace('Mei는 관찰 내용을 기록한다.',replacements[change])
    elif change=='source':current['source']=current['source'].replace('Mei records','Mei discards');current['final']=current['final'].replace('Mei는 관찰 내용을 기록한다.','Mei는 관찰 내용을 폐기한다.')
    elif change=='context':current['context']='Different context'
    elif change=='neighbors':current['neighbors']=['Changed factual content']
    elif change=='boundary':current['final']+=' 새 주장이다.'
    elif change=='reorder':current['final']=current['final'].replace('Mei는 관찰 내용을 기록한다.','TEMP').replace('Hana는 관찰 내용을 기록한다.','Mei는 관찰 내용을 기록한다.').replace('TEMP','Hana는 관찰 내용을 기록한다.')
    else:current['source']+=' {v1}.'
    assert delta_checks(old,current)=={}


def test_new_omission_is_still_sent_to_auditor_and_cannot_pass():
    old=evidence(paragraph());current=copy.deepcopy(old);preserve(current)
    current['final']=current['final'].replace('Mei는 관찰 내용을 기록한다.','Mei는 기록한다.');current.pop('assurance')
    def request(messages,schema):
        data=json.loads(messages[1]['content']);assert all(k not in data for k in ['PREVIOUS_VERDICTS','CACHED_APPROVAL'])
        return json.dumps([dict(id=x['id'],verdict='partial' if x['id'] in {'s2','t2'} else 'faithful',evidence=[('t' if x['side']=='source' else 's')+x['id'][1:]],reason='observation content omitted' if x['id'] in {'s2','t2'} else '') for x in data['UNITS'] if x['id'] in data['CHECK_IDS']])
    current['assurance']=audit(current,request)
    assert not accepted(current) and current['assurance']['status']=='repair'
    assert any(c['verdict']=='partial' for c in current['assurance']['checks'])


def test_changed_evidence_invalidates_transitive_dependents():
    old=evidence(paragraph());old['assurance']['checks'][7]['evidence']=['t2']
    current=copy.deepcopy(old);current['final']=current['final'].replace('Mei는 관찰 내용을 기록한다.','Mei는 현장 기록을 작성한다.')
    kept=delta_checks(old,current)
    assert 's7' not in kept and 't7' not in kept


@pytest.mark.parametrize('case',['source_reference','label','fragment'])
def test_nonlocal_context_and_fragment_guards(case):
    old=paragraph()
    if case=='source_reference':old['source']+=' This observation depends on the preceding result.';old['final']+=' 이 관찰은 앞의 결과에 의존한다.'
    if case=='fragment':old['final']=old['final'].replace('Luis는 관찰 내용을 기록한다.','Luis는 관찰 내용을 기록하며;')
    evidence(old);current=copy.deepcopy(old)
    current['final']=current['final'].replace('Mei는 관찰 내용을 기록한다.','Mei는 현장 기록을 작성한다.')
    if case=='label':current['label']='title'
    assert delta_checks(old,current)=={}
