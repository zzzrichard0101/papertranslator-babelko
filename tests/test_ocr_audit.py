import pytest

from scripts.audit_ocr_corpus import compare


def test_repeated_words_and_missing_ocr_are_counted():
    result = compare('The moon and the moon', 'The moon and noise')
    assert result['reference_words'] == 5
    assert result['matched_words'] == 3
    assert result['missing'] == ['the', 'moon']
    assert result['extra'] == ['noise']
    assert result['recall'] == .6


def test_empty_label_cannot_claim_full_recall():
    assert compare('', '')['recall'] is None


def test_phantom_tildes_are_extra_ocr_content():
    assert compare('Only participants', '~~ Only participants')['extra'] == ['~~']
