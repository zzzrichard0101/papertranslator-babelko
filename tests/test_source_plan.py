import json
from unittest.mock import patch

from babelko.hybrid import HybridTranslator, errors, grounded_numeric_repeat, record_errors
from babelko.translator import number_errors, validate_items
from babelko.source_plan import failure_summary, identifier_errors, locked_identifiers, profile


def test_preflight_locks_exact_identifiers_without_freezing_descriptive_prose():
    source=('Use LLaVA-665K and CAMBRIAN-7M with the source '
            'https://doi.org/10.1234/example. The Ours-30K row is a description.')
    tokens=locked_identifiers(source)
    assert tokens==['LLaVA-665K','CAMBRIAN-7M','https://doi.org/10.1234/example']
    assert locked_identifiers('https://doi.org/10. {v1}1234/example')==[]
    assert profile(source)['risk']=='high'
    assert not identifier_errors('Ours-30K','우리 방법-30K')
    assert identifier_errors('Use LLaVA-665K.','LLaVA-650K를 사용한다.')
    assert not identifier_errors('Use LLaVA-665K.','LLaVA-665K를 사용한다.')
    assert not number_errors('Use LLaVA-665K with 24 examples.',
                             '24개 예시에 LLaVA-665K를 사용한다.')
    try:
        validate_items([dict(id=0,input='Use LLaVA-665K.')],
                       [dict(id=0,output='CAMBRIAN-665K를 사용한다.')])
    except ValueError as error:
        assert '보호 식별자' in str(error)
    else:
        raise AssertionError('A changed model identifier was accepted')


def test_pdf_wrapped_dataset_suffix_compares_as_the_same_identifier():
    source='Use VISION-FLAN-ICONS- 37K and LLAVA- 665K; compare LLAVA-665K.'
    target='VISION-FLAN-ICONS-37K와 LLAVA-665K를 사용하고 LLAVA-665K와 비교한다.'
    assert not identifier_errors(source,target)
    assert not number_errors(source,target)
    assert identifier_errors(source,target.replace('37K','36K'))
    assert number_errors(source,target.replace('37K','36K'))


def test_single_evidenced_patch_recovers_a_numeric_identifier_without_full_rewrite(tmp_path):
    source='Use LLaVA-665K with 24 examples.'
    draft='24개 예시에 LLaVA-650K를 사용한다.'
    assert errors(source,draft)
    translator=object.__new__(HybridTranslator)
    translator.checkpoints=tmp_path
    translator.stats={}
    translator.hard_failures=[]
    translator.retries=0
    calls=[]

    def request(messages,schema=None):
        calls.append(messages)
        assert schema and 'DRAFT' in messages[1]['content']
        return json.dumps(dict(id=0,decision='patch',patches=[
            dict(evidence='LLaVA-665K',before='LLaVA-650K',after='LLaVA-665K')]))

    translator._request=request
    record=dict(key='one-number',source=source,label='text',context='',draft=draft,
                draft_errors=errors(source,draft),source_profile=profile(source))
    translator.retranslate(record)
    assert len(calls)==1
    assert record['final']=='24개 예시에 LLaVA-665K를 사용한다.'
    assert record['decision']=='targeted_structural_patch'
    assert not errors(source,record['final'])
    assert translator.stats['targeted_repairs']==1


def test_failure_summary_retains_uncertainty_instead_of_auto_passing():
    report=failure_summary([
        dict(error='숫자·부호·출현 수 불일치'),
        dict(error='영어 본문·제목 미번역'),
        dict(error='문장별 원문·번역 대조에서 반복 오류')])
    assert report['total']==3
    assert report['by_kind']==dict(quantity=1,untranslated_or_identifier=1,meaning_review=1)
    assert 'do not distinguish' in report['interpretation']


def test_repeated_quantity_requires_a_fresh_bilingual_audit(tmp_path):
    from babelko.assurance import REVISION, fingerprint, tasks

    source='We add 1 and then subtract it from the threshold.'
    target='임계값에 1을 더한 뒤 1을 뺀다.'
    assert grounded_numeric_repeat(source,target)
    assert not grounded_numeric_repeat(source,'임계값에 1을 더한 뒤 2를 뺀다.')
    assert not grounded_numeric_repeat('We add 1 and subtract 1.',target)
    assert errors(source,target)
    translator=object.__new__(HybridTranslator)
    translator.checkpoints=tmp_path
    translator.stats={}
    translator.hard_failures=[]
    translator.cancel=lambda:False
    translator._request=lambda *args: (_ for _ in ()).throw(AssertionError('unnecessary rewrite'))
    record=dict(key='pronoun',source=source,label='text',context='',draft=target,
                draft_errors=errors(source,target))

    def faithful(candidate,*args):
        pieces=tasks(candidate['source'],candidate['final'])
        checks=[]
        for item in pieces:
            opposite='t0' if item['side']=='source' else 's0'
            checks.append(dict(id=item['id'],verdict='faithful',evidence=[opposite],reason=''))
        return dict(revision=REVISION,fingerprint=fingerprint(candidate),checks=checks)

    with patch('babelko.assurance.audit',side_effect=faithful):
        translator.retranslate(record)
    assert record['final']==target
    assert record['decision']=='audited_heuristic_exception'
    assert not record_errors(record)
