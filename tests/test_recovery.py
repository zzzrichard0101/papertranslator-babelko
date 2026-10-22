import json,copy,threading
from types import SimpleNamespace as NS
import pytest
from babelko.scan_evidence import corrections,ordered_rows
from babelko.recovery import consensus,bound_to_source,ScanRecovery
from babelko.assurance import reconsider,tasks,fingerprint,REVISION,accepted


def test_independent_ocr_words_are_sorted_on_baselines_before_anchor_checks():
    source='The authors suggest that we learn 10 use the catalogue correctly.'
    rows=[dict(text='use the catalogue correctly.',score=.99,bbox=[250,103,400,116]),
          dict(text='The authors suggest that we learn',score=.99,bbox=[10,100,220,118]),
          dict(text='to',score=.99,bbox=[225,105,245,115])]
    value,edits=corrections(source,rows)
    assert value==source.replace('10','to') and len(edits)==1


def test_two_ocr_readings_need_independent_support_to_resolve_disagreement():
    assert consensus('data in order','data 1n order','data in order')=='data in order'
    assert consensus('Draft writing ne An editor asked to revise.',
                     'Draft writing An editor asked i revise.',
                     'Draft writing An editor asked to revise. I resubmit.',
                     'An editor may be asked to revise. I resubmit.')=='Draft writing  An editor asked to revise.'
    assert consensus('10 patients','20 patients','10 20 patients') is None
    assert consensus('No effect was observed','An effect was observed','effect was observed') is None


def test_recovered_paragraph_cannot_absorb_next_or_previous_paragraph():
    source='But if we return to the premise, art therapy has value.'
    ocr='Previous sentence ended. But if we return to the premise, art therapy has value. Taking the idea further would be a new paragraph.'
    assert bound_to_source(ocr,source)=='But if we return to the premise, art therapy has value.'
    assert bound_to_source('But if we return to the premise only.',source) is None


def test_recovered_paragraph_edges_accept_scanner_overprints_only_when_both_match():
    original='DDeespsitpeite tthhee findings, the participant had borderline personality sdisorder.'
    scanned='Despite the findings, the participant had borderline personality disorder.'
    assert bound_to_source(scanned,original)==scanned
    assert bound_to_source('data from year to year, or Next topic begins.',
                           'ddataa ta ffrormom yveeartoar to year, or')=='data from year to year, or'
    assert bound_to_source('ERIC, CINAHL;',"EERRICIC, <style id='4'>C</style>CINIANHIAHL;")=='ERIC, CINAHL;'


def test_good_source_does_not_trigger_scan_rereading():
    recovery=object.__new__(ScanRecovery);recovery.failed={'A different source.'}
    recovery.observe=lambda _:pytest.fail('unfailed source triggered OCR')
    value=NS(unicode='The source is valid.',placeholders=[])
    assert recovery(value,None,{})==(value,[])


def test_failed_scan_recovery_keeps_only_its_paragraph_and_requires_two_readers(monkeypatch):
    import babeldoc.format.pdf.document_il.midend.il_translator as native
    class Formula:
        def __init__(self,n,char):
            self.placeholder='{v'+str(n)+'}'
            self.formula=NS(pdf_character=[NS(char_unicode=char)])
    monkeypatch.setattr(native,'FormulaPlaceholder',Formula)
    source='D{v1}r{v2}a{v3}f{v4}t{v5} writing is a process.'
    answer='Draft writing is a process.'
    rows=[dict(text=answer+' The next paragraph begins here.',score=.99,bbox=[0,0,100,10])]
    recovery=object.__new__(ScanRecovery);recovery.failed={source};recovery.lock=threading.RLock()
    recovery.observe=lambda _:dict(rows=rows,second_rows=copy.deepcopy(rows))
    value=NS(unicode=source,placeholders=[Formula(i,c) for i,c in enumerate('raftx',1)])
    result,changes=recovery(value,None,dict(rows=rows))
    assert result.unicode==answer and result.placeholders==[]
    assert changes[0]['action']=='pixel_consensus_fragmented_scan_prose'
    # A disagreement without independent evidence cannot replace the source.
    recovery.observe=lambda _:dict(rows=rows,second_rows=[dict(text='Different unrelated text.',score=.99,bbox=[0,0,100,10])])
    value=NS(unicode=source,placeholders=[Formula(i,c) for i,c in enumerate('raftx',1)])
    assert recovery(value,None,dict(rows=[]))[1]==[]


def test_failed_scan_recovery_never_flattens_math_even_if_ocr_agrees(monkeypatch):
    import babeldoc.format.pdf.document_il.midend.il_translator as native
    class Formula:
        def __init__(self,n,char):
            self.placeholder='{v'+str(n)+'}'
            self.formula=NS(pdf_character=[NS(char_unicode=char)])
    monkeypatch.setattr(native,'FormulaPlaceholder',Formula)
    source='D{v1}r{v2}a{v3}f{v4}t{v5} writing is a process.'
    row=dict(text='Draft writing is a process.',score=.99,bbox=[0,0,100,10])
    recovery=object.__new__(ScanRecovery);recovery.failed={source};recovery.lock=threading.RLock()
    recovery.observe=lambda _:dict(rows=[row],second_rows=[row])
    value=NS(unicode=source,placeholders=[Formula(i,c) for i,c in enumerate('raft=',1)])
    assert recovery(value,None,dict(rows=[row]))==(value,[])
    assert value.unicode==source and len(value.placeholders)==5


def failing_record():
    r=dict(source='Use the device only if dry.',final='장치가 건조한 경우에만 사용한다.',context='',label='text')
    r['assurance']=dict(revision=REVISION,fingerprint=fingerprint(r),status='repair',
        checks=[dict(**t,verdict='partial',evidence=[],reason='alleged omission') for t in tasks(r['source'],r['final'])])
    return r


def test_challenge_retains_original_findings_and_full_source_and_target():
    r=failing_record();old=copy.deepcopy(r['assurance'])
    def request(messages,schema):
        data=json.loads(messages[1]['content'])
        assert ' '.join(t['text'] for t in data['UNITS'] if t['side']=='source')==r['source']
        assert ' '.join(t['text'] for t in data['UNITS'] if t['side']=='target')==r['final']
        return json.dumps([dict(id=t['id'],verdict='faithful',evidence=['t0' if t['side']=='source' else 's0'],reason='Complete condition is present.') for t in data['UNITS']])
    result=reconsider(r,r['assurance'],request)
    assert r['assurance']==old and result['status']=='passed'
    assert len(result['reconsideration']['original_findings'])==len(tasks(r['source'],r['final']))
    r['assurance']=result;assert accepted(r)


@pytest.mark.parametrize('evidence',[[],['s0'],['t99']])
def test_challenge_cannot_withdraw_a_finding_without_valid_opposite_evidence(evidence):
    r=failing_record()
    def request(*_):return json.dumps([dict(id=t['id'],verdict='faithful',evidence=evidence if t['id']=='s0' else ['t0' if t['side']=='source' else 's0'],reason='') for t in tasks(r['source'],r['final'])])
    with pytest.raises(ValueError):reconsider(r,r['assurance'],request)


def test_challenge_cannot_reuse_old_candidate_or_ignore_cancellation():
    r=failing_record();r['final']='장치를 사용한다.'
    with pytest.raises(ValueError):reconsider(r,r['assurance'],lambda *_:pytest.fail('stale request'))
    r=failing_record()
    with pytest.raises(InterruptedError):reconsider(r,r['assurance'],lambda *_:pytest.fail('cancelled request'),lambda:True)
