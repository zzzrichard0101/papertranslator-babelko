import json,threading
from unittest.mock import patch
import pytest
from babelko.hybrid import errors,apply_patches,HybridTranslator,context_hints,split_source,NUMBER_SPINE,auditable_issues,record_errors,override_fingerprint,VALIDATION_POLICY_REVISION,retry_feedback
from babelko.translator import validate_items
from types import SimpleNamespace


@pytest.mark.parametrize('source,target',[
    ('Published on 6 October 1944.','1944년 10월 6일에 출판되었다.'),
    ('Published in December 2026.','2026년 12월에 출판되었다.'),
    ('July5 - 10, 2020.','2020년 7월 5일~10일.'),
    ('6October1944','1944년 10월 6일'),
    ('Use zero-order SH and 4 bands.','0차 SH와 4개 밴드를 사용한다.'),
    ('Initialize with zeros in algorithm 1.','알고리즘 1에서 0으로 초기화한다.'),
    ('The third hand.','제3의 손.'),
    ('The Eleventh Conference in 2023.','2023년 제11회 학회.'),
    ('2 Billion Points (jul 2022), 17 pages.','20억 개의 점 (2022년 7월), 17쪽.'),
    ('30K iterations','3만 회 반복'),
    ('Ours-30K','우리 방법-30K'),
    ('Use 7K and 30K iterations.','7000회와 30000회 반복한다.'),
    ('Use 1-5K points.','1000~5000개의 점을 사용한다.'),
    ('Use 1-5 million Gaussians.','100만~500만 개의 가우시안을 사용한다.'),
    ('Use 1 to 5 million Gaussians.','1-5백만 개의 가우시안을 사용한다.'),
    ('https://doi.org/10. 1111/test.123','https://doi.org/10.1111/test.123'),
    ('Art as Therapy with Children (1971)','아동과 함께하는 치료로서의 미술 (1971)'),
    ('Flexibility (relationships, decision making).','유연성 (관계, 의사결정).'),
    ('HPC resources from GENCI-IDRIS (Grant 2022).','GENCI-IDRIS의 HPC 자원(Grant 2022).'),
    ('InstantNGP (Base) uses 35K iterations.','InstantNGP의 기본 설정(Base)은 35K회 반복한다.'),
    ("<style id='1'>Algorithm 2</style>3D model", "<style id='1'>알고리즘 2</style>3D 모델"),
])
def test_equivalent_numeric_forms(source,target):
    assert not errors(source,target)


def test_wrapped_method_with_benchmark_value_is_not_a_code_call():
    source='The method beats En- doGSLAM(0.65 FPS) on the benchmark.'
    target='이 방법은 벤치마크에서 EndoGSLAM(0.65 FPS)보다 우수하다.'
    assert not errors(source,target)


def test_machine_asset_identifiers_are_preserved_as_literal_data():
    from babelko.hybrid import literal
    value='c2_transverse1_t3_v3 c2_transverse1_t4_v3 c2_transverse2_t1_v2'
    assert literal(value)
    assert not errors(value,value)
    assert not literal('The c2_transverse1_t3_v3 file contains measurements.')


def test_repeated_diagram_identifiers_keep_their_exact_occurrences():
    from babelko.hybrid import literal
    row='MLP 3DGS MLP 3DGS MLP 3DGS MLP 3DGS'
    assert literal(row)
    assert not literal('3DGS NETWORK ARCHITECTURE')
    assert errors(row,row[:-5])


def test_model_repeating_a_long_styled_translation_is_rejected():
    source=("<style id='1'>Dip et al</style><style id='3'>: NeuroSleepNet: "
            'An Explainable Multi-Head Attention-Based Framework with Spatial Learning</style>')
    clause='NeuroSleepNet: 공간 학습을 이용한 설명 가능한 다중 헤드 어텐션 기반 프레임워크'
    doubled=f"<style id='1'>Dip et al</style>: {clause}<style id='3'>Dip et al</style>: {clause}"
    assert '번역문 앞부분 반복' in errors(source,doubled)
    assert '번역문 앞부분 반복' not in errors(source,
        "<style id='1'>Dip 외</style><style id='3'>: 공간 학습을 이용한 설명 가능한 다중 헤드 어텐션 기반 프레임워크</style>")


def test_retry_feedback_preserves_valid_korean_month_numeral():
    source='The event happened on February 3.'
    translated='이 사건은 2월 3일에 발생했다.'
    feedback=retry_feedback(source,translated,'서식 태그 순서 오류')
    assert '"numeric_equivalence_passed": true' in feedback
    assert 'Keep those quantities unchanged' in feedback
    assert '"raw_extra"' not in feedback
    missing=retry_feedback(source,'이 사건은 2월에 발생했다.','숫자 누락')
    assert '"numeric_equivalence_passed": false' in missing
    assert '"raw_missing"' in missing


def test_unique_dataset_identifier_row_is_literal_but_heading_is_not():
    from babelko.hybrid import literal
    row='MME SQA-I POPE VQAv2 LLaVA-W'
    assert literal(row)
    assert not errors(row,row)
    assert not literal('3DGS NETWORK ARCHITECTURE')
    assert not literal('The model uses MME and VQAv2 for evaluation.')


def test_standalone_formula_with_native_placeholders_is_literal_not_english_prose():
    from babelko.hybrid import literal
    equation="<style id='1'>6 </style>c{v3}<style id='4'>(</style>Y{v6}V{v7}Y{v8}w{v9}<style id='10'>)</style>{v12}Y{v13}V{v14}<style id='15'>ˆ</style>C{v17}"
    assert literal(equation)
    assert not literal('We use {v1}, {v2}, and {v3} in the method.')


def test_compact_iteration_time_label_replaces_clipped_prose_candidate(tmp_path):
    from babelko.hybrid import compact_metric_label
    from babelko.storage import read
    assert compact_metric_label('25 It. 12.8s')=='25회 12.8초'
    assert compact_metric_label('The method used 25 It. 12.8s') is None
    t=object.__new__(HybridTranslator);t.folder=tmp_path;t.checkpoints=tmp_path;t.cancel=lambda:False
    t.stats={'reviewed':0};t.hard_failures=[]
    record=dict(key='metric',source='25 It. 12.8s',draft='25번 항목. 소요 시간: 12.8초',
        final='25번 항목. 소요 시간: 12.8초',label='text',context='')
    t.units={'metric':record};t.audit_batch=lambda records:None
    t.ensure_assured=lambda row:None
    t.review(lambda *_:None)
    assert record['final']=='25회 12.8초' and record['decision']=='compact_figure_metric'
    assert read(tmp_path/'metric.json')['final']=='25회 12.8초'


@pytest.mark.parametrize('source,target',[
    ('The coefficient is nonzero in (26).','계수는 0이 아니며 식 (26)에 나타난다.'),
    ('The profile isaone-dimensional Gaussian.','프로파일은 1차원 가우스 분포이다.'),
    ('One quarter of the tiles is selected from 4 images.','4개 이미지에서 타일의 1/4만 선택한다.'),
])
def test_written_quantities_and_korean_fraction_suffixes(source,target):
    assert not errors(source,target)
    if '1/4' in target:assert errors(source,target.replace('1/4','1/3'))


def test_only_uncertain_heuristics_can_use_audited_exception():
    source='This method compares ModelScore(x) with the baseline.'
    target='이 방법은 기본 방식과 모델 점수를 비교한다.'
    assert auditable_issues(source,target)==['코드 함수 식별자 변경']
    assert not auditable_issues('function ModelScore(x) returns 24.','함수 모델 점수는 24를 반환한다.')
    assert not auditable_issues('The value is 24.','값은 42이다.')
    record=dict(source=source,final=target,label='text',heuristic_override=dict(
        revision=VALIDATION_POLICY_REVISION,issues=auditable_issues(source,target),
        fingerprint=override_fingerprint(source,target,'text',auditable_issues(source,target))))
    assert record_errors(record)  # A signed override without independent audit is insufficient.


def test_heuristic_exception_requires_current_full_audit_and_exact_target(tmp_path):
    from babelko.assurance import REVISION,fingerprint
    source='This method compares ModelScore(x) with the baseline.'
    target='이 방법은 기본 방식과 모델 점수를 비교한다.'
    translator=object.__new__(HybridTranslator)
    translator.checkpoints=tmp_path;translator.cancel=lambda:False;translator.hard_failures=[]
    translator.stats={};translator._request=lambda *a:None
    record=dict(key='case',source=source,label='text',context='',draft=target,final_error='earlier failed')
    def faithful(candidate,*args):
        return dict(revision=REVISION,fingerprint=fingerprint(candidate),checks=[
            dict(id='s0',verdict='faithful',evidence=['t0'],reason=''),
            dict(id='t0',verdict='faithful',evidence=['s0'],reason='')])
    with patch('babelko.assurance.audit',side_effect=faithful):
        assert translator.accept_audited_heuristic(record,[target])
    assert record_errors(record)==[]
    assert record['decision']=='audited_heuristic_exception'
    assert 'final_error' not in record
    record['final']=target+' 추가 내용'
    assert record_errors(record)
    record['final']=target
    record['neighbors']=['Different source neighbor']
    assert record_errors(record)  # Context changes invalidate the previous evidence.


def test_heuristic_exception_rejects_negative_audit_and_hard_failures(tmp_path):
    from babelko.assurance import REVISION,fingerprint
    translator=object.__new__(HybridTranslator)
    translator.checkpoints=tmp_path;translator.cancel=lambda:False;translator.hard_failures=[]
    translator.stats={};translator._request=lambda *a:None
    source='This method compares ModelScore(x) with the baseline.'
    target='이 방법은 기본 방식과 모델 점수를 비교한다.'
    record=dict(key='case',source=source,label='text',context='')
    def negative(candidate,*args):
        return dict(revision=REVISION,fingerprint=fingerprint(candidate),checks=[
            dict(id='s0',verdict='partial',evidence=['t0'],reason='Method identifier omitted.'),
            dict(id='t0',verdict='faithful',evidence=['s0'],reason='')])
    with patch('babelko.assurance.audit',side_effect=negative):
        assert not translator.accept_audited_heuristic(record,[target])
    assert 'final' not in record
    hard=dict(key='number',source='The value is 24.',label='text',context='')
    with patch('babelko.assurance.audit',side_effect=AssertionError('hard guard must not audit')):
        assert not translator.accept_audited_heuristic(hard,['값은 42이다.'])


def test_retranslation_falls_back_to_independent_audit_after_repair_retries(tmp_path):
    from babelko.assurance import REVISION,fingerprint
    translator=object.__new__(HybridTranslator)
    translator.checkpoints=tmp_path;translator.cancel=lambda:False;translator.hard_failures=[]
    translator.stats={};translator.retries=0
    source='This method compares ModelScore(x) with the baseline.'
    target='이 방법은 기본 방식과 모델 점수를 비교한다.'
    calls=[]
    def request(*args):calls.append(args);return target
    translator._request=request
    record=dict(key='retry',source=source,label='text',context='',draft=target)
    def faithful(candidate,*args):
        return dict(revision=REVISION,fingerprint=fingerprint(candidate),checks=[
            dict(id='s0',verdict='faithful',evidence=['t0'],reason=''),
            dict(id='t0',verdict='faithful',evidence=['s0'],reason='')])
    with patch('babelko.assurance.audit',side_effect=faithful):
        translator.retranslate(record)
    assert len(calls)==3
    assert translator.retries==2
    assert record['final']==target and not record_errors(record)
    assert not translator.hard_failures


def test_failed_edit_can_recover_a_faithful_saved_draft(tmp_path):
    from babelko.assurance import REVISION,fingerprint
    source='One quarter of the tiles is selected from 4 images.'
    draft='4개 이미지에서 타일의 1/4만 선택한다.'
    final='4개 이미지에서 타일 일부만 선택한다.'
    record=dict(key='draft',source=source,label='text',context='',draft=draft,final=final,
        final_error='meaning mismatch')
    record['assurance']=dict(revision=REVISION,fingerprint=fingerprint(record),checks=[
        dict(id='s0',verdict='partial',evidence=['t0'],reason='Fraction omitted.'),
        dict(id='t0',verdict='faithful',evidence=['s0'],reason='')])
    translator=object.__new__(HybridTranslator)
    translator.checkpoints=tmp_path;translator.cancel=lambda:False;translator.hard_failures=[]
    translator.stats={};translator._request=lambda *a:None
    def faithful(candidate,*args):
        return dict(revision=REVISION,fingerprint=fingerprint(candidate),checks=[
            dict(id='s0',verdict='faithful',evidence=['t0'],reason=''),
            dict(id='t0',verdict='faithful',evidence=['s0'],reason='')])
    with patch('babelko.assurance.audit',side_effect=faithful):
        assert translator.try_checked_draft(record)
    assert record['final']==draft and not record_errors(record)
    assert 'final_error' not in record


@pytest.mark.parametrize('source,target',[
    ('The value is -24.','값은 24이다.'),
    ('The value is 24.','값은 42이다.'),
    ('Initialize with zeros in algorithm 1.','알고리즘 1에서 2로 초기화한다.'),
    ('July5 - 10, 2020.','2020년 7월 6일~10일.'),
    ('2 Billion Points in 2022.','2022년의 30억 개 점.'),
    ('Use -7K points.','7000개의 점을 사용한다.'),
    ('Use 30K points.','3000개의 점을 사용한다.'),
    ('Use 2 billion points.','2만 개의 점을 사용한다.'),
    ('Use 1-5 million Gaussians.','100만~600만 개의 가우시안을 사용한다.'),
    ('Use 1-5 million Gaussians.','500만 개의 가우시안을 사용한다.'),
    ('Use zero-order SH and 4 bands.','0차 SH와 5개 밴드를 사용한다.'),
    ("<style id='1'>Algorithm 2</style>3D model", "<style id='1'>알고리즘 23</style>D 모델"),
    ('2 RELATED WORK','2 RELATED WORK'),
    ('REFERENCES','REFERENCES'),
    ('{v1}IdentifyTileRanges({v2},{v3})','{v1}타일범위식별({v2},{v3})'),
    ('function Rasterize({v1})','함수 래스터화({v1})'),
    ('The book was published in October.','이 책은 10월에 출판되었다. 在那里'),
])
def test_translation_contract_failures(source,target):
    assert errors(source,target)


def test_ocr_spaced_program_code_is_preserved_without_hiding_prose():
    from babelko.hybrid import literal
    assert literal('in t f ( void ) { i n t a {v1}; f o r ( ; ; ) { a {v2}; a -{v3}; } }')
    assert literal('long f ( ) { long x {v1}; f o r ( i n t i {v2}; i {v3}; {v4}i ) { w h i le ( x {v5}) { i f ( x % {v6}) { x {v7}; } } } r e t u r n x ; }')
    assert not literal('The function for calculating a score (x) uses two inputs; it returns a sum.')


def test_compact_program_fragments_and_identifier_series_are_literal():
    from babelko.hybrid import literal

    for source in (
        '#!{v1}no{v2}main {v3}#{v4}no{v5}mangle {v6}pub fn f ( a : i 3 2 ) -{v7}i 3 2 { 0 }',
        'i n t f ( i n t a ) { re t ur n 0 ; }',
        'func f ( a : I n t ) -{v1}I n t { r etu rn a }',
        "<style id='1'>for </style><style id='3'>c </style><style id='5'>in range</style><style id='7'>(board size )</style>{v9}",
        "<style id='1'>r1 val </style>{v3}<style id='4'>model . evaluate (R1 ). as </style><style id='6'>long </style><style id='8'>()</style>",
        'FAM-111B/161A/72D/201A/216A/169A/83D/86A/72A/120C/86C2P',
    ):
        assert literal(source), source
    for prose in (
        'For each subject in range of the scanner, we measured signal strength.',
        'The model evaluates R1 and then reports a longer duration.',
        'If no subject has a matching record, the analysis is incomplete.',
        ('We demonstrate the proof by writing model.evaluate(x).asLong() as a small example. '
         'The surrounding paragraph explains why the model remains stable for all conditions. ' * 4),
    ):
        assert not literal(prose), prose


def test_patch_must_quote_source_and_revalidate_whole_target():
    source='The study does not support the claim; 24 people participated.'
    draft='연구는 주장을 지지한다. 24명이 참여했다.'
    value=dict(decision='patch',patches=[dict(evidence='does not support',before='지지한다',after='지지하지 않는다')])
    assert apply_patches(source,draft,value)=='연구는 주장을 지지하지 않는다. 24명이 참여했다.'
    value['patches'][0]['evidence']='not in source'
    with pytest.raises(ValueError):apply_patches(source,draft,value)
    with pytest.raises(ValueError):apply_patches(source,draft.replace('24','42'),dict(decision='keep',patches=[]))


def test_native_protocol_and_foreign_example_are_not_document_context():
    prompt='Return JSON. 你好\n## Contextual Hints for Better Translation\n1. First title in full text: Art Therapy\n2. The most recent title is: Defense\n## Here is the input:'
    assert context_hints(prompt)=='1. First title in full text: Art Therapy\n2. The most recent title is: Defense'


def test_long_reference_units_split_without_losing_text_or_style_boundaries():
    text=("A. Author. 2020. <style id='1'>Journal of Graphics.</style> 24, 1-3. "*80)+'Final sentence.'
    parts=split_source(text)
    assert len(parts)>1 and ''.join(parts)==text
    assert all(len(p)<1900 and p.count('<style')==p.count('</style>') for p in parts)


def test_long_styled_sentences_split_only_after_complete_style_spans():
    source=("<style id='1'>"+'A complete sentence about the method. '*12+"</style>"
            "<style id='3'>"+'Another complete sentence about the result. '*12+"</style>")
    parts=split_source(source,650)
    assert len(parts)==2 and ''.join(parts)==source
    assert all(part.count('<style')==part.count('</style>') for part in parts)
    assert split_source("<style id='1'>Conjecture 2.</style>{v3}the authors explain this.",20)==[
        "<style id='1'>Conjecture 2.</style>{v3}the authors explain this."]


def test_job_checkpoint_replay_is_local_and_never_reuses_broken_draft(tmp_path):
    def instance():
        t=object.__new__(HybridTranslator);t.folder=tmp_path;t.checkpoints=tmp_path/'hybrid';t.checkpoints.mkdir(exist_ok=True)
        t.phase='draft';t.units={};t.cancel=lambda:False;t.translate_cache_call_count=0;t.hard_failures=[]
        t.stats=dict(drafted=0,literals=0,replayed=0);t._request=lambda *a:'값은 24이다.'
        return t
    t=instance();assert t.unit('The value is 24.','text','context')=='값은 24이다.'
    r=next(iter(t.units.values()));r['final']='값은 24이다.'
    from babelko.assurance import REVISION,fingerprint
    r['assurance']=dict(revision=REVISION,fingerprint=fingerprint(r),checks=[dict(id='s0',verdict='faithful',evidence=['t0'],reason=''),dict(id='t0',verdict='faithful',evidence=['s0'],reason='')]);t.checkpoint(r)
    t=instance();t.phase='replay';t._request=lambda *a:pytest.fail('replay used inference')
    assert t.unit('The value is 24.','text','context')=='값은 24이다.'
    assert t.unit('{v1}IdentifyTileRanges({v2},{v3})','text','')=='{v1}IdentifyTileRanges({v2},{v3})'


def test_staged_native_replay_uses_pristine_il_and_restores_source_titles(tmp_path):
    from babelko.hybrid import staged_layout
    import babeldoc.format.pdf.high_level as high
    events=[];docs=SimpleNamespace(page=[dict(text='source')])
    config=SimpleNamespace(shared_context_cross_split_part=SimpleNamespace(first_paragraph='original title',recent_title_paragraph='original section'))
    translator=SimpleNamespace(folder=tmp_path,stats={},units={},hard_failures=[],phase='draft')
    translator.save_summary=lambda:None;translator.assurance_summary=lambda:dict(status='passed')
    translator.reconcile_failures=lambda:None
    def review(progress):events.append('review');translator.phase='replay'
    translator.review=review
    class Native:
        def __init__(self,t,c):self.translation_config=c
        def translate(self,document):
            events.append((translator.phase,document.page[0]['text'],config.shared_context_cross_split_part.first_paragraph))
            document.page[0]['text']=translator.phase+' target'
            config.shared_context_cross_split_part.first_paragraph='mutated title'
    with patch('babeldoc.format.pdf.document_il.midend.il_translator_llm_only.ILTranslatorLLMOnly',Native),patch('babelko.text_structure.caption_word_repairs',lambda _:{}):
        with staged_layout(translator,lambda:events.append('switch'),lambda *a:None):
            high.ILTranslatorLLMOnly(translator,config).translate(docs)
    assert events==[('draft','source','original title'),'switch','review',('replay','source','original title')]
    assert docs.page[0]['text']=='replay target'


def test_il_snapshot_handles_deep_layout_and_keeps_shared_links():
    from dataclasses import dataclass
    from babelko.hybrid import snapshot_pages
    from babeldoc.format.pdf.document_il.frontend.il_creater_active_support import LazyPassthroughInstruction,PassthroughSnapshot

    @dataclass(slots=True)
    class Node:
        child: object

    shared=Node('original')
    lazy=LazyPassthroughInstruction(PassthroughSnapshot())
    root=[shared,shared,lazy]
    for _ in range(1200):root=[root]
    saved=snapshot_pages(root)
    original=root;copied=saved
    for _ in range(1200):
        original=original[0];copied=copied[0]
    assert copied[0] is copied[1]
    assert copied[0] is not original[0]
    assert copied[2] is lazy
    shared.child='changed'
    assert copied[0].child=='original'


def test_dense_style_translation_batches_nonempty_segments_without_losing_tags():
    source=''.join(f"<style id='{i}'>문장{i}</style>" for i in range(12))
    t=object.__new__(HybridTranslator);t.cancel=lambda:False
    calls=[]
    def request(messages,schema):
        payload=json.loads(messages[1]['content']);calls.append(len(payload['SOURCE_SEGMENTS']))
        return json.dumps(payload['SOURCE_SEGMENTS'],ensure_ascii=False)
    t._request=request
    assert t.protected_translation(source,dict(label='text',context=''),numeric_failure=False)==source
    assert calls==[5,5,2]


def test_dense_style_batches_allow_numeric_phrase_to_cross_style_boundary():
    from babelko.translator import number_errors
    parts=['문장']*12;parts[5]='2D 위치';parts[6]='3DGS에서'
    source=''.join(f"<style id='{i}'>{part}</style>" for i,part in enumerate(parts))
    t=object.__new__(HybridTranslator);t.cancel=lambda:False
    def request(messages,schema):
        values=json.loads(messages[1]['content'])['SOURCE_SEGMENTS']
        return json.dumps([v.replace('2D 위치','2D 위치 3DGS').replace('3DGS에서','에서') for v in values],ensure_ascii=False)
    t._request=request
    target=t.protected_translation(source,dict(label='text',context=''),numeric_failure=False)
    assert '2D 위치 3DGS</style><style id=\'6\'>에서' in target
    assert not number_errors(source,target)


def test_leading_bullet_is_preserved_without_treating_it_as_a_count():
    t=object.__new__(HybridTranslator)
    calls=[]
    def request(messages):
        calls.append(json.loads(messages[1]['content'])['SOURCE'])
        return '의뢰부터 첫 면담까지, 평가부터 치료 시작까지 걸리는 시간.'
    t._request=request
    source='{v1}times between referral and first meeting, and assessment and beginning therapy.'
    target=t.protected_translation(source,dict(context='',formula_hints={'{v1}':'•'}),numeric_failure=False)
    assert target=='{v1}의뢰부터 첫 면담까지, 평가부터 치료 시작까지 걸리는 시간.'
    assert calls==[source[len('{v1}'):]]
    assert errors(source,'{v1}의뢰와 첫 만남 사이의 횟수')
    assert not errors(source,target)


def test_cancelled_draft_makes_no_request_or_checkpoint(tmp_path):
    t=object.__new__(HybridTranslator);t.cancel=lambda:True
    with pytest.raises(InterruptedError):t.unit('The value is 24.','text','')


def test_valid_checkpoint_with_stale_failure_is_reused_without_translation(tmp_path):
    from babelko.assurance import REVISION,fingerprint
    t=object.__new__(HybridTranslator);t.folder=tmp_path;t.checkpoints=tmp_path;t.cancel=lambda:False
    t.stats=dict(reviewed=0);t.hard_failures=[]
    r=dict(key='saved',source='The study included 24 participants.',final='연구에는 24명이 참여했다.',label='text',context='',neighbors=[],final_error='old failure')
    r['assurance']=dict(revision=REVISION,fingerprint=fingerprint(r),checks=[
        dict(id='s0',verdict='faithful',evidence=['t0'],reason=''),dict(id='t0',verdict='faithful',evidence=['s0'],reason='')])
    t.units={'saved':r};t._request=lambda *_:pytest.fail('valid saved unit requested inference')
    t.recover_segments=lambda *_:pytest.fail('valid saved unit was retranslated')
    t.review(lambda *_:None)
    assert t.phase=='replay' and t.stats['review_cache_hits']==1 and not r.get('final_error')


def test_layout_memory_reuses_exact_prose_candidate_but_never_old_assurance(tmp_path):
    from babelko.storage import save
    t=object.__new__(HybridTranslator);t.layout_input=tmp_path/'Layout-input.pdf';t.checkpoints=tmp_path;t.stats={}
    old=dict(key='old',source="The study <style id='1'>included 24 participants</style> and did not establish causality.",
        final="연구에는 <style id='1'>24명이 참여했으며</style>, 인과관계를 입증하지 못했다.",label='text',assurance={'status':'passed'})
    save(tmp_path/'old.json',old)
    recovered=t.layout_candidate('The study included 24 participants and did not establish causality.','text')
    assert recovered and '24명' in recovered['draft'] and 'assurance' not in recovered
    assert t.layout_candidate('The study included 42 participants and did not establish causality.','text') is None
    assert t.layout_candidate('The study included {v1} participants and did not establish causality.','text') is None


def test_contact_identifier_lists_are_preserved_without_requiring_korean():
    from babelko.hybrid import literal
    source='alice@example.org,bob@university.edu,carol@lab.example.com'
    assert literal(source) and not errors(source,source)
    assert literal('https://example.org/a/long/path/with/several/english/words')
    assert not literal('The estimate is invalid. Contact alice@example.org for details.')


def test_korean_output_cannot_hide_an_untranslated_clause_but_names_and_tokens_survive():
    source='This design ensures, to the extent possible, that the packets are indistinguishable.'
    assert errors(source,'이 설계는 to the extent possible 패킷을 구별할 수 없게 한다.')
    assert not errors(source,'이 설계는 가능한 한 패킷을 구별할 수 없게 한다.')
    assert not errors('National Institute of Standards and Technology provides guidance.',
                      'National Institute of Standards and Technology는 지침을 제공한다.')
    assert not errors('Read {v1}. See https://example.org/a/path/to/the/page for details.',
                      '{v1}을 읽으세요. 자세한 내용은 https://example.org/a/path/to/the/page 참조.')
    assert errors('processes are','processes are')
    assert not errors('processes are','과정은')


def test_literal_identifier_is_restored_from_source_even_if_cached_final_is_wrong(tmp_path):
    t=object.__new__(HybridTranslator);t.folder=tmp_path;t.checkpoints=tmp_path;t.phase='draft';t.units={};t.cancel=lambda:False
    t.stats={'literals':0,'replayed':0};t.translate_cache_call_count=0;t._request=lambda *_:pytest.fail('literal requested inference')
    source='alice@example.org,bob@university.edu'
    assert t.unit(source,'text','')==source
    p=next(tmp_path.glob('*.json'));r=json.loads(p.read_text('utf-8'));r['final']='Changed contact';r['final_error']='stale failure';p.write_text(json.dumps(r),'utf-8')
    t.units={};t.phase='replay'
    assert t.unit(source,'text','')==source
    assert not next(iter(t.units.values())).get('final_error')


def test_checkpoint_cannot_substitute_another_source_under_an_existing_key(tmp_path):
    t=object.__new__(HybridTranslator);t.folder=tmp_path;t.checkpoints=tmp_path/'hybrid';t.checkpoints.mkdir()
    t.phase='draft';t.units={};t.cancel=lambda:False;t.translate_cache_call_count=0;t.stats={'drafted':0}
    t._request=lambda *_:'값은 24이다.'
    t.unit('The value is 24.','text','')
    p=next(t.checkpoints.glob('*.json'));value=json.loads(p.read_text('utf-8'));value['source']='A different document.'
    p.write_text(json.dumps(value),'utf-8');t.units={}
    with pytest.raises(ValueError,match='체크포인트'):t.unit('The value is 24.','text','')


def test_repeated_placeholder_loss_uses_program_owned_spine(tmp_path):
    t=object.__new__(HybridTranslator);t.checkpoints=tmp_path;t.retries=0;t.stats={'retranslated':0};t.hard_failures=[]
    calls=[];replies=iter(['값은 24이다.','값은 24이다.',json.dumps(['값은',' 24이다.'])])
    def request(messages,schema=None):calls.append(schema);return next(replies)
    t._request=request
    record=dict(key='record',source='The value {v1} is 24.',label='text',context='')
    t.retranslate(record)
    assert record['final']=='값은{v1} 24이다.' and record['protected_spine']
    assert calls[-1]['minItems']==calls[-1]['maxItems']==2
    assert not t.hard_failures


def test_numeric_style_marked_quantity_is_one_indivisible_fallback_token(tmp_path):
    source="over all 44<style id='1'>,</style>850 pairs of frames."
    token="44<style id='1'>,</style>850"
    assert NUMBER_SPINE.findall(source)==[token]
    assert NUMBER_SPINE.split(source)==['over all ',' pairs of frames.']
    t=object.__new__(HybridTranslator);t.checkpoints=tmp_path;t.retries=0;t.stats={'retranslated':0};t.hard_failures=[]
    replies=iter(["총 44개의 <style id='1'>,</style>850쌍의 프레임."]*2+[json.dumps(['총 ','쌍의 프레임에 걸쳐.'])])
    t._request=lambda *args:next(replies)
    record=dict(key='styled-number',source=source,label='text',context='',final_error='숫자·부호·출현 수 불일치')
    t.retranslate(record)
    assert record['final']=="총 44<style id='1'>,</style>850쌍의 프레임에 걸쳐."
    assert not errors(source,record['final']) and record['protected_spine']


def test_numeric_retry_identifies_an_invented_precision_and_keeps_verbal_quantity(tmp_path):
    source='The two curves differ by a few tenths of a decibel.'
    bad='두 곡선의 차이는 0.1dB다.'
    good='두 곡선은 데시벨의 몇십분의 몇 정도 차이가 난다.'
    assert errors(source,bad) and not errors(source,good)
    assert errors(source,'두 곡선은 데시벨의 몇 분의 일 정도 차이가 난다.')
    assert not errors(source,'두 곡선은 데시벨의 십분의 몇 정도 차이가 난다.')
    t=object.__new__(HybridTranslator);t.checkpoints=tmp_path;t.retries=0;t.stats={'retranslated':0};t.hard_failures=[]
    calls=[]
    def request(messages,schema=None):
        calls.append(messages)
        return bad if len(calls)==1 else good
    t._request=request
    record=dict(key='verbal-number',source=source,label='text',context='')
    t.retranslate(record)
    assert record['final']==good and '"raw_extra": {"0.1": 1}' in calls[1][-1]['content']
    assert '십분의 몇' in calls[0][0]['content']


def test_meaning_repair_requires_fresh_bidirectional_evidence_then_reuses_it(tmp_path):
    from babelko.assurance import accepted
    t=object.__new__(HybridTranslator);t.checkpoints=tmp_path;t.cancel=lambda:False;t.retries=0
    t.stats=dict(patched=0,retranslated=0);t.hard_failures=[]
    record=dict(key='meaning',source='The method does not guarantee recovery.',final='이 방법은 복구를 보장한다.',label='text',context='')
    calls=[]
    def request(messages,schema=None):
        calls.append(messages[0]['content'])
        data=json.loads(messages[1]['content'])
        if 'CHECK_IDS' in data:
            bad=any('보장한다.' in x['text'] for x in data['UNITS'] if x['side']=='target')
            values=[dict(id=x['id'],verdict='contradiction' if bad else 'faithful',
                evidence=['t0'] if x['side']=='source' else ['s0'],reason='negation reversed' if bad else '') for x in data['UNITS'] if x['id'] in data['CHECK_IDS']]
            return json.dumps([[v[k] for k in ['id','verdict','evidence','reason']] for v in values] if schema['items']['type']=='array' else values)
        return json.dumps(dict(id=0,decision='patch',patches=[dict(evidence='does not guarantee',before='보장한다',after='보장하지 않는다')]))
    t._request=request;t.ensure_assured(record)
    assert accepted(record) and record['final']=='이 방법은 복구를 보장하지 않는다.'
    assert len(calls)==3 and t.stats['repair_rounds']==1
    t.ensure_assured(record);assert len(calls)==3


def test_repeated_meaning_failure_stops_without_success_or_infinite_retries(tmp_path):
    t=object.__new__(HybridTranslator);t.checkpoints=tmp_path;t.cancel=lambda:False;t.stats={};t.hard_failures=[]
    r=dict(key='meaning',source='Never stop.',final='멈춘다.',label='text',context='')
    count=[]
    def request(messages,schema=None):
        count.append(1);data=json.loads(messages[1]['content'])
        values=[dict(id=x['id'],verdict='contradiction',evidence=['t0'] if x['side']=='source' else ['s0'],reason='negation reversed') for x in data['UNITS'] if x['id'] in data['CHECK_IDS']]
        return json.dumps([[v[k] for k in ['id','verdict','evidence','reason']] for v in values] if schema['items']['type']=='array' else values)
    t._request=request;t.repair_meaning=lambda *_:None
    with pytest.raises(RuntimeError):t.ensure_assured(r)
    assert len(count)==4 and t.hard_failures and r['assurance']['status']=='repair'
    assert r['assurance']['reconsideration']['withdrawn']==[]


def test_review_defers_one_bad_unit_processes_other_units_then_recovers(tmp_path):
    from babelko.storage import read
    t=object.__new__(HybridTranslator);t.folder=tmp_path;t.checkpoints=tmp_path;t.cancel=lambda:False
    t.stats={'reviewed':0,'replayed':0};t.hard_failures=[];events=[]
    a=dict(key='a',source='The first result is valid.',final='첫 결과는 유효하다.',label='text',context='')
    b=dict(key='b',source='The second result is valid.',final='둘째 결과는 유효하다.',label='text',context='')
    t.units={'a':a,'b':b};failed=[False]
    def ensure(record):
        events.append(record['key'])
        if record is a and not failed[0]:failed[0]=True;raise ValueError('injected unit defect')
        t.clear_failure(record)
    t.ensure_assured=ensure;t.recover_segments=lambda record:events.append('recover-'+record['key']);t.audit_batch=lambda records:None
    t.review(lambda *_:None)
    assert events==['a','b','recover-a','a']
    assert t.phase=='replay' and not t.hard_failures and not a.get('final_error')
    assert read(tmp_path/'pending-review.json')['pending']==[]


def test_unresolved_unit_uses_source_in_replay_and_remains_retryable(tmp_path):
    from babelko.storage import read
    t=object.__new__(HybridTranslator);t.folder=tmp_path;t.checkpoints=tmp_path;t.cancel=lambda:False
    t.stats={'reviewed':0,'replayed':0};t.hard_failures=[];events=[]
    t.units={k:dict(key=k,source='The result '+k+' is valid.',final='결과는 유효하다.',label='text',context='') for k in ['a','b']}
    def ensure(record):
        events.append(record['key'])
        if record['key']=='a':raise ValueError('persistent defect')
    t.ensure_assured=ensure;t.recover_segments=lambda _:None;t.audit_batch=lambda records:None
    t.review(lambda *_:None)
    assert events==['a','b','a','a'] and t.phase=='replay'
    assert [r['key'] for r in read(tmp_path/'pending-review.json')['pending']]==['a']
    assert t.unresolved_keys=={'a'} and t.assurance_summary()['status']=='failed'
    assert t.unit(t.units['a']['source'],'text','')==t.units['a']['source']


def test_new_replay_failure_keeps_source_and_checkpoint(tmp_path):
    from babelko.storage import read
    t=object.__new__(HybridTranslator);t.folder=tmp_path;t.checkpoints=tmp_path;t.cancel=lambda:False
    t.phase='replay';t.units={};t.hard_failures=[];t.stats={'replayed':0};t.unresolved_keys=set()
    source='The method is accurate.'
    t.retranslate=lambda record: (_ for _ in ()).throw(ValueError('unit review failed'))
    assert t.unit(source,'text','')==source
    record=next(iter(t.units.values()))
    assert record['key'] in t.unresolved_keys
    assert read(tmp_path/'pending-review.json')['pending'][0]['key']==record['key']
    assert read(tmp_path/(record['key']+'.json'))['final_error']=='unit review failed'
    assert t.hard_failures and t.assurance_summary()['status']=='failed'
    t.hard_failures.append(dict(source=source,error='duplicate retry'))
    t.reconcile_failures()
    assert t.hard_failures==[dict(key=record['key'],source=source,error='unit review failed')]


def test_segmented_recovery_commits_only_a_complete_validated_candidate(tmp_path):
    t=object.__new__(HybridTranslator);t.checkpoints=tmp_path;t.cancel=lambda:False;t.retries=0
    t.hard_failures=[];t.stats={'retranslated':0};calls=[]
    source='The study included 24 participants. '*50
    r=dict(key='long',source=source,final='이전 후보',label='text',context='',final_error='first failure')
    t.hard_failures.append(dict(source=source,error='first failure'))
    def request(messages):
        part=json.loads(messages[1]['content'])['SOURCE_FRAGMENT'];calls.append(part)
        return part.replace('The study included 24 participants.','연구에는 24명이 참여했다.')
    t._request=request;t.recover_segments(r)
    assert len(calls)>1 and not errors(source,r['final'])
    assert r['decision']=='segmented_retranslation' and not t.hard_failures and not r.get('final_error')
    previous=r['final'];t._request=lambda *args:'연구에는 42명이 참여했다.'
    with pytest.raises(ValueError):t.recover_segments(r)
    assert r['final']==previous


def test_segmented_recovery_reuses_only_valid_completed_fragments(tmp_path):
    t=object.__new__(HybridTranslator);t.checkpoints=tmp_path;t.cancel=lambda:False;t.retries=0
    t.hard_failures=[];t.stats={'retranslated':0}
    source='The study included 24 participants. '*50
    parts=split_source(source,650);assert len(parts)>1
    record=dict(key='partial',source=source,label='text',context='',final_error='previous failure')
    first_calls=[]
    def fail_later(messages):
        part=json.loads(messages[1]['content'])['SOURCE_FRAGMENT'];first_calls.append(part)
        return part.replace('The study included 24 participants.','연구에는 24명이 참여했다.') if len(first_calls)==1 else part
    t._request=fail_later
    with pytest.raises(ValueError):t.recover_segments(record)
    assert record['segment_recovery']['targets'][0] and record['segment_recovery']['targets'][1] is None
    assert (tmp_path/'partial.json').is_file()
    from babelko.storage import read
    record=read(tmp_path/'partial.json')  # Simulate process restart.
    resumed=[]
    def succeed(messages):
        part=json.loads(messages[1]['content'])['SOURCE_FRAGMENT'];resumed.append(part)
        return part.replace('The study included 24 participants.','연구에는 24명이 참여했다.')
    t._request=succeed;t.recover_segments(record)
    assert len(resumed)==len(parts)-1 and record['decision']=='segmented_retranslation'
    assert 'segment_recovery' not in record and not errors(source,record['final'])


def test_known_defect_is_repaired_before_a_fresh_audit_without_rechecking_old_candidate(tmp_path):
    from babelko.assurance import REVISION,fingerprint,accepted
    t=object.__new__(HybridTranslator);t.checkpoints=tmp_path;t.cancel=lambda:False;t.stats={};t.hard_failures=[];calls=[]
    r=dict(key='known',source='Never stop.',final='멈춘다.',label='text',context='')
    r['assurance']=dict(revision=REVISION,fingerprint=fingerprint(r),checks=[dict(id='s0',verdict='contradiction',evidence=['t0'],reason='negation'),dict(id='t0',verdict='contradiction',evidence=['s0'],reason='negation')])
    def repair(record,issues):calls.append('repair');record['final']='멈추지 않는다.'
    t.repair_meaning=repair
    def request(messages,schema):
        calls.append('audit');data=json.loads(messages[1]['content'])
        assert any(x['text']=='멈추지 않는다.' for x in data['UNITS'])
        values=[dict(id=x['id'],verdict='faithful',evidence=['t0'] if x['side']=='source' else ['s0'],reason='') for x in data['UNITS']]
        return json.dumps([[v[k] for k in ['id','verdict','evidence','reason']] for v in values] if schema['items']['type']=='array' else values)
    t._request=request;t.ensure_assured(r)
    assert calls==['repair','audit'] and accepted(r)


def test_recovered_candidate_is_saved_before_review_and_survives_restart(tmp_path):
    from babelko.storage import read
    def instance():
        t=object.__new__(HybridTranslator);t.folder=tmp_path;t.checkpoints=tmp_path;t.cancel=lambda:False
        t.phase='draft';t.units={};t.translate_cache_call_count=0;t.hard_failures=[];t.stats={}
        t._request=lambda *_:pytest.fail('saved layout candidate triggered translation')
        return t
    t=instance();t.recovered_candidate=lambda *_:dict(draft='연구에는 24명이 참여했다.',draft_errors=[],source_recovery=dict(previous_key='previous'))
    source='The study included 24 participants.'
    assert t.unit(source,'text','')=='연구에는 24명이 참여했다.'
    saved=read(next(tmp_path.glob('*.json')))
    assert saved['source']==source and saved['source_recovery']['previous_key']=='previous'
    t=instance();t.recovered_candidate=lambda *_:pytest.fail('saved candidate needed recovery again')
    assert t.unit(source,'text','')=='연구에는 24명이 참여했다.'


def test_disposable_source_collection_does_not_replace_real_draft_or_final(tmp_path):
    t=object.__new__(HybridTranslator);t.folder=tmp_path;t.checkpoints=tmp_path;t.cancel=lambda:False
    t.phase='draft';t.units={};t.translate_cache_call_count=0;t.hard_failures=[];t.stats={'drafted':0}
    t.recovered_candidate=lambda *_:None;t._request=lambda *_:'연구에는 24명이 참여했다.';t.collect_source_only=True
    source='The study included 24 participants.'
    assert t.unit(source,'text','')==source
    record=next(iter(t.units.values()));assert record['draft']=='연구에는 24명이 참여했다.'
    record['final']='연구에는 24명이 참여했다.';t.collect_source_only=False
    assert t.unit(source,'text','')==record['final']


def test_resume_catalog_order_is_independent_of_native_worker_completion(tmp_path):
    from babelko.storage import save,read
    t=object.__new__(HybridTranslator);t.folder=tmp_path;t.checkpoints=tmp_path;t.cancel=lambda:False
    t.stats={'reviewed':0};t.hard_failures=[]
    t.units={k:dict(key=k,label='text',source='The result '+k+' is valid.',final='결과는 유효하다.',context='') for k in ['c','a','b']}
    save(tmp_path/'unit-order.json',dict(active_keys=['a','b','c']))
    events=[];t.audit_batch=lambda _:None;t.ensure_assured=lambda r:events.append(r['key'])
    t.review(lambda *_:None)
    assert events==['a','b','c']
    assert read(tmp_path/'pending-review.json')['active_keys']==['a','b','c']
    assert t.units['b']['neighbors']==[t.units['a']['source'],t.units['c']['source']]


def test_scan_recovery_revisits_accepted_numeric_fallback_using_original_draft(tmp_path):
    from babelko.hybrid import scan_recovery_records
    from babelko.storage import save
    good=dict(key='good',source='The group had 10 participants.',
        draft='집단에는 10명이 있었다.',final='집단에는 10명이 있었다.')
    artifact=dict(key='artifact',source='They had the means 10 control the group.',
        draft='그들은 집단을 통제할 수단이 있었다.',final='그들에게는 10 집단을 통제할 수단이 있었다.')
    for record in (good,artifact):save(tmp_path/(record['key']+'.json'),record)
    assert [r['key'] for r in scan_recovery_records(tmp_path,[])]==['artifact']


def test_scan_recovery_revisits_failed_glyph_fragments_after_review_list_clears(tmp_path):
    from babelko.hybrid import scan_recovery_records
    from babelko.storage import save
    broken=dict(key='glyphs',source='D{v1}r{v2}a{v3}f{v4}t{v5} writing is important.',
        formula_hints={f'{{v{i}}}':c for i,c in enumerate('raftx',1)},
        final_error='영어 본문·제목 미번역')
    save(tmp_path/'glyphs.json',broken)
    assert [r['key'] for r in scan_recovery_records(tmp_path,[])]==['glyphs']


def test_coordinated_count_and_types_cannot_collapse_to_count_only():
    source='Describe the number and types of levels in the outline.'
    assert '병렬 개념 누락: 원문의 개수와 유형을 모두 명시하세요.' in errors(
        source,'개요가 몇 가지 수준으로 구성되는지 설명한다.')
    assert not errors(source,'개요를 이루는 수준의 수와 유형을 설명한다.')
