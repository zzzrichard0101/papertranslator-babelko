import pytest

from babelko.quantity_relations import errors
from babelko.translator import validate_items
from babelko.validation import quantity_relation_status
from babelko.storage import save


@pytest.mark.parametrize(('source', 'faithful', 'reversed'), [
    ('The samples contained 5 mg and 10 g.',
     '시료에는 5밀리그램과 10그램이 들어 있었다.',
     '시료에는 5그램과 10밀리그램이 들어 있었다.'),
    ('The spacers measured 5 mm and 10 cm.',
     '간격재의 길이는 5 mm와 10 cm였다.',
     '간격재의 길이는 5 cm와 10 mm였다.'),
    ('The first file was 5 MB and the second was 10 GB.',
     '첫 파일은 5메가바이트, 두 번째는 10기가바이트였다.',
     '첫 파일은 5기가바이트, 두 번째는 10메가바이트였다.'),
    ('The two readings were 5 kPa and 10 MPa.',
     '두 측정값은 5킬로파스칼과 10메가파스칼이었다.',
     '두 측정값은 5메가파스칼과 10킬로파스칼이었다.'),
    ('The concentrations were 5 mg/dL and 10 mmol/L.',
     '농도는 5 mg/dL와 10 mmol/L였다.',
     '농도는 5 mmol/L와 10 mg/dL였다.'),
])
def test_unit_swaps_with_same_number_multiset(source, faithful, reversed):
    assert errors(source, faithful) == []
    assert errors(source, reversed) == ['수치와 단위의 대응이 원문과 다릅니다.']
    with pytest.raises(ValueError):
        validate_items([dict(id=0, input=source)], [dict(id=0, output=reversed)])


def test_explicit_variable_values_cannot_swap_while_numbers_remain_equal():
    source = 'The calibrated parameters were alpha=5 and beta=10.'
    assert errors(source, '보정된 매개변수는 alpha=5 및 beta=10이었다.') == []
    wrong = '보정된 매개변수는 alpha=10 및 beta=5였다.'
    assert errors(source, wrong) == ['식별자와 수치의 대응이 원문과 다릅니다.']
    with pytest.raises(ValueError, match='식별자와 수치'):
        validate_items([dict(id=0, input=source)], [dict(id=0, output=wrong)])


def test_group_values_are_bound_even_when_unit_multiset_is_unchanged():
    source = 'Group A received 5 mg, whereas Group B received 10 mg.'
    faithful = 'B군은 10밀리그램, A군은 5밀리그램을 투여받았다.'
    wrong = 'A군은 10밀리그램, B군은 5밀리그램을 투여받았다.'
    assert errors(source, faithful) == []
    assert errors(source, wrong) == ['집단 식별자와 수치의 대응이 원문과 다릅니다.']
    with pytest.raises(ValueError, match='집단 식별자와 수치'):
        validate_items([dict(id=0, input=source)], [dict(id=0, output=wrong)])


def test_group_check_declines_ambiguous_or_quantity_first_syntax():
    source = 'Group A had 5 participants and received 10 mg; Group B had 8 participants and received 20 mg.'
    target = 'A군은 8명이며 20 mg, B군은 5명이며 10 mg을 받았다.'
    assert errors(source, target) == []
    source = 'Group A received 5 mg and Group B received 10 mg.'
    target = '5 mg을 A군에, 10 mg을 B군에 투여했다.'
    assert errors(source, target) == []


def test_only_explicit_bindings_are_enforced():
    # No inferred bilingual mapping or English/Korean word-order assumption.
    assert errors('The control group received 5 mg.', '대조군은 5밀리그램을 투여받았다.') == []
    assert errors('The length was 5 m.', '길이는 5미터였다.') == []
    assert errors('The temperature was 20 °C.', '온도는 섭씨 20도였다.') == []
    assert errors('The figure labels x=5 and y=10.', '그림의 표기는 x가 5이고 y가 10이다.') == []
    assert errors('The dose was 5 mg.', '용량은 5㎎이었다.') == []


def test_style_tags_do_not_break_numeric_unit_binding():
    source = "<style id='1'>5</style> mg and 10 kg"
    target = "<style id='1'>5</style>밀리그램과 10킬로그램"
    assert errors(source, target) == []


def test_shared_range_unit_is_not_a_false_mismatch():
    assert errors('The dose ranged from 5 mg to 10 mg.', '용량은 5~10밀리그램이었다.') == []
    assert errors('The rate was 5% to 10%.', '비율은 5~10%였다.') == []
    assert errors('The dose ranged from 5 mg to 10 mg.', '용량은 5~10그램이었다.')


def test_cached_tracking_output_is_rechecked_after_translation(tmp_path):
    path=tmp_path/'translate_tracking.json'
    source='Group A received 5 mg; Group B received 10 mg.'
    wrong='A군은 10 mg, B군은 5 mg을 받았다.'
    save(path,dict(page=[dict(paragraph=[dict(pdf_unicode=source,input=source,output=wrong)])]))
    report=quantity_relation_status(path)
    assert report['status']=='failed' and report['checked_units']==1
    assert report['issues'][0]['tracked_unit']==0
    save(path,dict(page=[dict(paragraph=[dict(pdf_unicode=source,input=source,
                                              output='A군은 5 mg, B군은 10 mg을 받았다.')])]))
    assert quantity_relation_status(path)['status']=='passed'


def test_explicit_technical_abbreviation_replacement_is_rejected():
    source='Magnetic resonance imaging (MRI) was performed.'
    assert errors(source,'자기공명영상(MRI)을 시행했다.') == []
    wrong='자기공명영상(CT)을 시행했다.'
    assert errors(source,wrong)==['정의된 전문용어의 괄호 속 약어가 다른 약어로 바뀌었습니다.']
    with pytest.raises(ValueError,match='약어'):
        validate_items([dict(id=0,input=source)],[dict(id=0,output=wrong)])
    # A faithful translation can omit the Latin abbreviation rather than
    # introducing a different parenthesized abbreviation.
    assert errors(source,'자기공명영상을 시행했다.') == []


def test_qwen_cache_identity_changes_with_relation_policy(tmp_path):
    from babelko.translator import KoreanTranslator
    from babelko.quantity_relations import REVISION
    from babelko.upstream import prepare
    prepare()
    from pdf2zh_next.config.model import SettingsModel,TranslationSettings
    from pdf2zh_next.config.translate_engine_model import OpenAISettings
    from pdf2zh_next.translator.base_rate_limiter import BaseRateLimiter
    settings=SettingsModel(translation=TranslationSettings(lang_out='ko'),
        translate_engine_settings=OpenAISettings(openai_model='synthetic',openai_base_url='http://127.0.0.1:1/v1',openai_api_key='unused'))
    translator=KoreanTranslator(settings,BaseRateLimiter(),tmp_path)
    try:
        assert translator.cache.params['babelko_relation_revision']==REVISION
    finally:
        translator.client.close()
