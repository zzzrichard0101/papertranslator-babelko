import collections,copy,hashlib,json,threading
import pytest
from babelko.preview import structurally_safe,PreviewTranslator
from babelko.policy import PROTOCOL


def instance(source,final,draft=None):
    t=object.__new__(PreviewTranslator);t.cancel=lambda:False;t.local=threading.local();t.visits=[];t.translate_cache_call_count=0
    key=hashlib.sha256(json.dumps([PROTOCOL,source,'text','',{}],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    row=dict(key=key,source=source,label='text',context='',final=final,draft=draft,final_error='unresolved')
    t.rows={key:row};t.by_source=collections.defaultdict(list,{(source,'text'):[row]})
    t._request=lambda *_:pytest.fail('preview used inference')
    return t,row


def test_preview_keeps_unverified_numeric_candidate_without_clearing_its_failure():
    source='The value {v1} is 24.';t,row=instance(source,'값 {v1}은 42이다.');before=copy.deepcopy(row)
    assert t.unit(source,'text','')=='값 {v1}은 42이다.'
    assert row==before and t.visits[-1]['selection']=='final'


def test_preview_unsafe_formula_candidate_uses_safe_draft_then_complete_source():
    source='The value {v1} is 24.';t,row=instance(source,'값은 42이다.','값 {v1}은 24이다.')
    assert t.unit(source,'text','')==row['draft'] and t.visits[-1]['selection']=='draft'
    row['draft']='값은 24이다.'
    assert t.unit(source,'text','')==source and t.visits[-1]['selection']=='source_unsafe_candidate'
    assert t.unit('A completely new fragment.','text','')=='A completely new fragment.'


def test_preview_rejects_misordered_tags_and_never_guesses_conflicting_contexts():
    source="<style id='1'>The value</style> is 24."
    assert not structurally_safe(source,"</style>값<style id='1'>은 24이다.")
    t,row=instance('A new result.','새 결과이다.');t.rows={}
    row['context']='section A';other={**row,'key':'other','context':'section B','final':'다른 뜻이다.'}
    t.by_source[(row['source'],'text')]=[row,other]
    assert t.unit(row['source'],'text','')==row['source']
