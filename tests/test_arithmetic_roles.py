import pytest

from babelko.arithmetic_roles import errors, source_claims
from babelko.assurance import segments
from babelko.hybrid import HybridTranslator, errors as translation_errors


@pytest.mark.parametrize('source,target', [
    ('We add 1 inside the square root and then subtract it.',
     '제곱근 안에 1을 더한 다음 그 값을 뺀다.'),
    ('We add 1 inside the square root and then subtract it.',
     '루트 내부에 1을 추가한 후 차감한다.'),
    ('Multiply 2 and divide it by the normalization factor.',
     '2를 곱한 뒤 정규화 계수로 나눈다.'),
])
def test_arithmetic_steps_accept_distinct_korean_wording(source, target):
    assert not errors(source, target)


@pytest.mark.parametrize('source,target', [
    ('We add 1 inside the square root and then subtract it.',
     '제곱근을 취한 뒤 1을 뺀다.'),
    ('We add 1 and then subtract it and add it back.',
     '1을 더한 뒤 뺀다.'),
    ('Multiply 2 and divide it by the normalization factor.',
     '정규화 계수로 2를 나눈다.'),
])
def test_arithmetic_steps_block_missing_operation(source, target):
    assert errors(source, target)
    assert any('연산 단계 누락' in issue for issue in translation_errors(source, target))


def test_actual_finance_failure_detects_missing_first_addition():
    source=('The reason we add 1 in the square root and then subtract it for above threshold values '
            'and add it back for below threshold values is because the square root function increases '
            'the input values which are less than 1, which would result in higher values for outliers '
            'the distance of which to the threshold is less than 1.')
    draft=('임계값보다 큰 값에 대해서는 제곱근 연산 후 1을 빼주고, 임계값보다 작은 값에 대해서는 '
           '다시 1을 더해주는 이유는 제곱근 함수가 1보다 작은 입력값들을 증가시키기 때문입니다.')
    claims = source_claims(source)
    assert [claim['operation'] for claim in claims] == ['add', 'subtract', 'add']
    assert claims[0]['scope'] == 'inside_square_root'
    assert errors(source, draft)
    parts = segments(source)
    assert len(parts) >= 3
    assert 'add 1 in the square root' in parts[0]


def test_single_operation_and_notation_are_left_to_bilingual_audit():
    assert not errors('Add 1 to the input.', '입력값에 1을 더한다.')
    assert not errors('Add 1 and subtract it.', 'x + 1 − 1로 계산한다.')


def test_missing_step_gets_source_grounded_retry_without_replacing_checkpoint(tmp_path):
    source = 'We add 1 inside the square root and then subtract it.'
    flawed = '제곱근을 취한 뒤 1을 뺀다.'
    corrected = '제곱근 안에 1을 더한 뒤 해당 값을 뺀다.'
    translator = object.__new__(HybridTranslator)
    translator.checkpoints = tmp_path
    translator.stats = {'retranslated': 0}
    translator.hard_failures = []
    translator.retries = 0
    translator.cancel = lambda: False
    sent = []

    def request(messages, schema=None):
        sent.append(messages)
        return flawed if len(sent) == 1 else corrected

    translator._request = request
    record = dict(key='arithmetic', source=source, label='text', context='', draft=flawed)
    translator.retranslate(record)
    assert record['final'] == corrected
    assert record['decision'] == 'retranslated'
    assert len(sent) == 2
    assert '연산 단계 누락' in sent[1][-1]['content']
    assert not translation_errors(source, record['final'])
