import importlib.util
from pathlib import Path

import pytest


SPEC = importlib.util.spec_from_file_location('accuracy_blind', Path(__file__).resolve().parents[1] / 'scripts' / 'accuracy_blind.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def pack():
    source = 'The intervention reduced risk only in patients who received the full dose.'
    return dict(items=[dict(item_id='case-1', document='paper', source=source,
                            source_sha256=MODULE.fingerprint(source),
                            label='text',
                            candidates=dict(hy_draft='초벌', qwen_single='단독', hybrid='최종'))])


def test_blind_review_is_deterministic_and_hides_method_names():
    review = MODULE.make_review(pack())
    assert review == MODULE.make_review(pack())
    assert set(review['items'][0]['options']) == {'A', 'B', 'C'}
    assert set(review['items'][0]['options'].values()) == {'초벌', '단독', '최종'}
    assert not any(method in str(review['items']) for method in MODULE.METHODS)


def test_no_score_without_full_independent_source_grounded_annotations():
    review = MODULE.make_review(pack())
    blank = dict(reviewer_id='external-1', independent_of_model_generation=True,
                 items=[dict(item_id='case-1', options={'A': [], 'B': [], 'C': []})])
    with pytest.raises(ValueError, match='attestation'):
        MODULE.score(pack(), review, {**blank, 'independent_of_model_generation': False})
    with pytest.raises(ValueError, match='Every blinded option'):
        MODULE.score(pack(), review, {**blank, 'items': [dict(item_id='case-1', options={'A': []})]})
    with pytest.raises(ValueError, match='quote'):
        MODULE.score(pack(), review, {**blank, 'items': [dict(item_id='case-1', options={
            'A': [dict(type='omission', severity='major', source_quote='invented', reason='missing')],
            'B': [], 'C': []})]})
    assert MODULE.score(pack(), review, blank)['units'] == 1
    first = next(letter for letter, value in review['items'][0]['options'].items() if value == '초벌')
    marked = dict(blank, items=[dict(item_id='case-1', options={
        letter: ([dict(type='omission', severity='major', source_quote='only',
                       reason='condition omitted')] if letter == first else [])
        for letter in ('A', 'B', 'C')})])
    result = MODULE.score(pack(), review, marked)
    assert result['methods']['hy_draft']['major_errors'] == 1
    assert result['methods']['hybrid']['major_errors'] == 0


def test_incomplete_comparison_is_excluded_from_blind_review():
    data = pack()
    del data['items'][0]['candidates']['qwen_single']
    assert MODULE.make_review(data)['items'] == []
    with pytest.raises(ValueError, match='No complete'):
        MODULE.score(data, MODULE.make_review(data), dict(reviewer_id='external-1',
                         independent_of_model_generation=True, items=[]))


def test_structural_report_counts_failed_baseline_as_unavailable(monkeypatch):
    import babelko.hybrid
    monkeypatch.setattr(babelko.hybrid, 'errors', lambda source, target, label: ['problem'] if target == '초벌' else [])
    data = pack()
    del data['items'][0]['candidates']['qwen_single']
    data['items'][0]['qwen_error'] = 'placeholder mismatch'
    report = MODULE.structural_report(data)
    assert len(report['methods']['hy_draft']['flagged']) == 1
    assert report['methods']['hybrid']['flagged'] == []
    assert report['methods']['qwen_single']['unavailable'][0]['error'] == 'placeholder mismatch'
