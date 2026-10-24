import pytest

from scripts.audit_ocr_corpus import compare,overlapping_lines


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


def test_same_words_in_wrong_order_do_not_pass_ordered_recall():
    result=compare('the mission will begin after launch','after launch the mission will begin')
    assert result['recall']==1
    assert result['ordered_recall']<1


def test_stray_brace_is_reported_as_unexpected_ocr():
    assert compare('-3-', 'EE -3- }')['extra']==['ee','}']


def test_visual_line_overlap_is_audited_separately_from_word_recall():
    import pymupdf as fitz
    with fitz.open() as doc:
        page=doc.new_page(width=300,height=100)
        page.insert_text((20,40),'First visible line',fontsize=14)
        page.insert_text((20,46),'Second visible line',fontsize=14)
        assert overlapping_lines(page,page.rect)
