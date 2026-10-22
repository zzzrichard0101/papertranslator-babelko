import copy,json,threading
from types import SimpleNamespace as NS
from unittest.mock import patch
import pytest
from babelko.review_pool import ReviewPool
from babelko.document_context import DocumentContext
from babelko.engine import LocalEngine


def record(key='a'):
    return dict(key=key,label='text',source='The result is valid.',final='결과는 유효하다.',context='')


def faithful(messages,schema):
    data=json.loads(messages[1]['content'])
    checks=[dict(id=x['id'],verdict='faithful',evidence=[v['id'] for v in data['UNITS'] if v['side']!=x['side'] and v.get('record_id')==x.get('record_id')],reason='') for x in data['UNITS'] if x['id'] in data['CHECK_IDS']]
    return json.dumps([[x[k] for k in ['id','verdict','evidence','reason']] for x in checks] if schema['items']['type']=='array' else checks)


def test_two_audits_overlap_without_mutating_records_and_commit_in_submission_order():
    barrier=threading.Barrier(2);owner=threading.get_ident();threads=[]
    def request(*args):
        threads.append(threading.get_ident());barrier.wait(timeout=3);return faithful(*args)
    rows=[record('a'),record('b')];before=copy.deepcopy(rows)
    pool=ReviewPool(request,lambda:False)
    try:
        for row in rows:pool.submit([row])
        with pytest.raises(RuntimeError):pool.submit([record('c')])
        outcomes=pool.drain()
    finally:pool.close()
    assert rows==before and len(set(threads))==2 and owner not in threads
    assert [group[0]['key'] for group,result in outcomes]==['a','b']
    assert all(result[0]['status']=='passed' for group,result in outcomes)


def test_stale_parallel_result_and_invalid_response_never_become_assurance():
    rows=[record()];pool=ReviewPool(faithful,lambda:False)
    try:
        pool.submit(rows);rows[0]['final']='오류가 있다.'
        assert pool.drain()==[(rows,None)]
        pool.request=lambda *_:'[]';pool.submit(rows)
        assert pool.drain()==[(rows,None)]
    finally:pool.close()
    assert 'assurance' not in rows[0]


def test_cancellation_propagates_and_leaves_input_unchanged():
    r=record();pool=ReviewPool(lambda *_:pytest.fail('cancelled request executed'),lambda:True)
    try:
        pool.submit([r])
        with pytest.raises(InterruptedError):pool.drain()
    finally:pool.close()
    assert 'assurance' not in r


def test_context_uses_exact_source_expansions_and_rejects_conflicts():
    ctx=DocumentContext([(1,'We discuss evidence based practice (EBP).'),(2,'Use randomized controlled trial (RCT).')])
    assert ctx.hints('EBP is important.')['definitions']['EBP']['expansion']=='evidence based practice'
    assert ctx.hints('RCT uses blinding.')['definitions']['RCT']['source_page']==2
    assert ctx.hints('This result was significant.') is None
    assert ctx.hints('XEBP is a different identifier.') is None
    ctx=DocumentContext([(1,'evidence based practice (EBP)'),(2,'electronic billing process (EBP)')])
    assert ctx.ambiguous==['EBP'] and ctx.hints('EBP') is None
    ctx=DocumentContext([(3,'We use evidence-based practice (EBP) in this chapter.')])
    assert ctx.entries['EBP']['quote']=='evidence-based practice (EBP)'


@pytest.mark.parametrize('phrase,short',[
    ('art- therapy','AT'),('evidence--based practice','EBP'),
    ('evidence---based practice','EBP'),('art-- therapy-','AT'),
    ('evidence-based- practice','EBP')])
def test_ocr_hyphen_fragments_cannot_crash_document_context(phrase,short):
    source='We discuss '+phrase+' ('+short+') in this chapter.'
    ctx=DocumentContext([(1,source),(2,'randomized controlled trial (RCT)')])
    assert ctx.entries[short]['quote']==phrase+' ('+short+')'
    assert ctx.entries[short]['quote'] in source
    assert ctx.hints(short)['definitions'][short]['source_page']==1
    assert ctx.entries['RCT']['expansion']=='randomized controlled trial'


def test_full_per_request_context_is_retained_for_two_slots():
    engine=object.__new__(LocalEngine);engine.registry={'review_slots':2}
    assert engine.capacity_args()==['-c','16384','-np','2']
    engine.registry={'review_slots':1};assert engine.capacity_args()==['-c','8192','-np','1']
    for bad in [0,3,True,'2']:
        engine.registry={'review_slots':bad}
        with pytest.raises(ValueError):engine.capacity_args()


def test_document_term_change_changes_checkpoint_identity_and_audit_input(tmp_path):
    from babelko.hybrid import HybridTranslator
    from babelko.assurance import fingerprint
    t=object.__new__(HybridTranslator);t.folder=tmp_path;t.checkpoints=tmp_path;t.cancel=lambda:False
    t.phase='draft';t.units={};t.translate_cache_call_count=0;t.stats={'drafted':0};t.hard_failures=[]
    t.recovered_candidate=lambda *_:None;prompts=[]
    t._request=lambda messages:prompts.append(messages) or 'EBP는 중요하다.'
    t.document_context=DocumentContext([(1,'evidence based practice (EBP)')])
    t.unit('EBP is important.','text','');a=copy.deepcopy(next(iter(t.units.values())))
    t.document_context=DocumentContext([(1,'electronic billing process (EBP)')]);t.units={}
    t.unit('EBP is important.','text','');b=next(iter(t.units.values()))
    assert a['key']!=b['key'] and fingerprint(a)!=fingerprint(b)
    assert 'evidence based practice' in a['context'] and 'electronic billing process' in b['context']
    assert 'evidence based practice' in prompts[0][0]['content']
