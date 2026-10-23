from babelko.semantic_guards import errors,repair
from babelko.hybrid import errors as hybrid_errors,saved_layout_candidate,trimmed_context_candidate
from babelko.storage import save


def test_monotonic_direction_reversal_is_rejected():
    source='The transmittance sequence is monotonically non-increasing.'
    wrong='투과율 수열은 단조비감소함수이다.'
    assert errors(source,wrong)
    assert hybrid_errors(source,wrong)
    assert not errors(source,'투과율 수열은 단조비증가 수열이다.')
    assert errors('The sequence is non-decreasing.','수열은 단조비증가한다.')


def test_placeholder_after_translated_thus_is_not_a_false_connector_error():
    assert not errors('The geometry, and thus {v19},{v20}, remains fixed.',
        '기하학적 구조와 따라서 {v19},{v20},는 고정된다.')
    assert errors('The matrix {v19},{v20} remains fixed.',
        '행렬은 따라서 {v19},{v20}, 고정된다.')


def test_technical_terms_and_scale_are_checked_without_banning_faithful_paraphrase():
    assert errors('Escape the exploitation-only trap.','활용(exploration)에만 의존하는 함정을 벗어난다.')
    assert errors('The gradient-dependent step is slow.','경도에 의존하는 단계는 느리다.')
    assert errors('It is orders of magnitude smaller.','이는 수 배(orders of magnitude) 작다.')
    assert not errors('The method balances exploration and exploitation.','이 방법은 탐색과 활용의 균형을 맞춘다.')
    assert errors('It uses gradient-driven exploitation.','기울기 기반 탐색을 사용한다.')
    assert errors('It has an exploitation-only bias.','개발(exploitation)에만 치우친 편향이다.')
    source='The exploitation-only deadlock is broken by exploration and balanced exploration-exploitation dynamics.'
    wrong='탐색 위주의 정체를 탐색으로 타개하고 탐색과 활용의 균형을 맞춘다.'
    assert errors(source,wrong)
    assert not errors(source,repair(source,wrong))
    source='The gradient is orders of magnitude smaller.'
    wrong='기울기는 몇 배나 작다.'
    assert errors(source,wrong)
    assert repair(source,wrong)=='기울기는 여러 자릿수만큼 작다.'


def test_exact_terminology_repair_keeps_protected_structure():
    source="<style id='1'>The gradient-dependent rule</style> uses Figure 7 and {v3}."
    target="<style id='1'>경도에 의존하는 규칙</style>은 그림 7과 {v3}을 사용한다."
    fixed=repair(source,target)
    assert fixed=="<style id='1'>기울기에 의존하는 규칙</style>은 그림 7과 {v3}을 사용한다."
    assert hybrid_errors(source,fixed)==[]
    assert repair('The bound is non-increasing.','상한은 단조비감소한다.')=='상한은 단조비증가한다.'


def test_open_ended_condition_keeps_its_scope_across_layout_lines():
    source='1: Build a tree by subdividing any node containing'
    wrong='1: 다음을 포함하는 모든 노드를 분할하여 트리를 구축한다.'
    fixed=repair(source,wrong)
    assert errors(source,wrong)
    assert fixed=='1: 다음을 포함하는 각각의 노드를 분할하여 트리를 구축한다.'
    assert not errors(source,fixed)


def test_previous_layout_candidate_requires_exact_source_and_single_record(tmp_path):
    record=dict(key='k',source='The gradient-dependent rule.')
    target='경도에 의존하는 규칙.'
    save(tmp_path/'region-ledger.json',dict(regions=[dict(record_keys=['k'],inputs=[record['source']],target=target)]))
    assert saved_layout_candidate(tmp_path,record)==target
    assert saved_layout_candidate(tmp_path,{**record,'source':'Different source.'}) is None


def test_prompt_context_echo_is_trimmed_only_when_remainder_passes_guards():
    source="<style id='1'>Incorporating </style>{v3}<style id='4'>into 3DGS improves fidelity.</style>"
    target="<style id='1'>{v3}를 </style><style id='4'>3DGS에 통합하면 충실도가 향상된다.</style>"
    record=dict(source=source,label='text',draft='CONTEXT는 번역 대상이 아닙니다: 2개 문장\n'+target)
    corrected="{v3}<style id='1'>를 </style><style id='4'>3DGS에 통합하면 충실도가 향상된다.</style>"
    assert errors(source,target)
    assert repair(source,target)==corrected
    assert trimmed_context_candidate(record)==corrected
    assert trimmed_context_candidate({**record,'draft':'설명: '+target}) is None
    assert trimmed_context_candidate({**record,'draft':'CONTEXT: '+target.replace('3DGS','4DGS')}) is None


def test_unstyled_context_echo_is_trimmed_only_with_faithful_remainder():
    source='The 7 chemical systems are stable.'
    target='7개 화학 반응계는 안정적이다.'
    record=dict(source=source,label='text',draft='문맥 정보: 문서 제목은 화학 반응 연구입니다.\n\n'+target)
    assert trimmed_context_candidate(record)==target
    assert trimmed_context_candidate({**record,'draft':'문맥 정보: 문서 제목은 화학 반응 연구입니다.\n\n원문'} ) is None


def test_dangling_page_boundary_word_and_formula_detachment():
    assert errors('The result is clear. As','결과는 명확하다. As')
    assert not errors('The result is clear. As','결과는 명확하다. 다음과 같이')
    assert errors('rendering order {v12}.','렌더링 순서에 따라 변한다.{v12}.')
    assert not errors('rendering order {v12}.','렌더링 순서 {v12}에 따라 변한다.')
    assert errors('reduce accumulated transmittance {v39},','누적 투과율을 줄이지만{v39},')
    assert errors('Incorporating {v3} into 3DGS improves fidelity.',"<style id='1'>에 </style>{v3}<style id='4'>를 3DGS에 통합하면 충실도가 향상된다.</style>")
    assert not errors('Incorporating {v3} into 3DGS improves fidelity.','{v3}를 3DGS에 통합하면 충실도가 향상된다.')
    source='Incorporating {v3} into 3DGS improves fidelity. However, integrating {v6} with exploration yields diminishing returns.'
    wrong='3DGS에 통합하면 충실도가 향상된다. 그러나 중요한 것은 {v3}을 탐색에 통합할 때 수익이 줄어든다. {v6}에서 보듯 그렇다.'
    assert errors(source,wrong)
