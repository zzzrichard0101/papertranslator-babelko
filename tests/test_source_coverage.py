from types import SimpleNamespace as Obj

import pymupdf
import pytest

from babelko.source_coverage import inspect, source_lines


FIRST = 'Independent source extraction detects missing research paragraphs today.'
SECOND = 'Additional experimental evidence remains outside parsed document content entirely.'


def document(pdf, *parsed):
    with pymupdf.open() as source:
        page = source.new_page(width=600, height=800)
        page.insert_text((45, 90), FIRST, fontsize=11)
        page.insert_text((45, 130), SECOND, fontsize=11)
        source.save(pdf)
    return Obj(page=[Obj(page_number=0,
                         pdf_paragraph=[Obj(unicode=value) for value in parsed])])


def test_native_source_line_missing_from_il_is_reported_without_changing_input(tmp_path):
    pdf = tmp_path / 'input.pdf'
    docs = document(pdf, FIRST)
    report = inspect(pdf, docs)
    assert report['status'] == 'diagnostic'
    assert report['candidate_lines'] == 2
    assert report['suspected_missing_lines'] == 1
    assert report['pages'][0]['suspected_missing'][0]['excerpt'] == SECOND
    assert docs.page[0].pdf_paragraph[0].unicode == FIRST


def test_complete_source_and_rich_style_text_do_not_trigger_missing_line(tmp_path):
    pdf = tmp_path / 'input.pdf'
    docs = document(pdf, "<style id='1'>" + FIRST + '</style>', SECOND)
    report = inspect(pdf, docs)
    assert report['suspected_missing_lines'] == 0


def test_no_native_text_layer_is_uninformative_not_certified(tmp_path):
    pdf = tmp_path / 'scan.pdf'
    with pymupdf.open() as source:
        source.new_page(width=600, height=800)
        source.save(pdf)
    report = inspect(pdf, Obj(page=[Obj(page_number=0, pdf_paragraph=[])]))
    assert report['candidate_lines'] == 0
    assert report['status'] == 'diagnostic'
    assert report['pages_without_prose_evidence'] == [1]
    assert 'not full source-image OCR recall' in report['scope']


def test_vertical_marginal_stamp_is_not_a_prose_omission_candidate():
    with pymupdf.open() as source:
        page = source.new_page(width=600, height=800)
        page.insert_text((32, 700),
                         'arXiv 2501 00640 version two math research December 2025',
                         fontsize=10, rotate=90)
        assert not list(source_lines(page))


def test_source_comparison_honors_job_cancellation(tmp_path):
    pdf = tmp_path / 'input.pdf'
    docs = document(pdf, FIRST, SECOND)
    with pytest.raises(InterruptedError):
        inspect(pdf, docs, cancel=lambda: True)


def test_independent_scan_evidence_is_compared_without_running_new_ocr(tmp_path):
    pdf = tmp_path / 'input.pdf'
    docs = document(pdf, FIRST)
    rows = {0: [dict(text=SECOND, bbox=[45, 115, 520, 135], score=.99),
                dict(text='Low confidence OCR should not count as evidence here',
                     bbox=[45, 150, 520, 170], score=.5)]}
    report = inspect(pdf, docs, pixel_rows=rows)
    assert report['pixel_checked_pages'] == 1
    assert report['pixel_candidate_rows'] == 1
    assert report['pixel_suspected_missing_rows'] == 1
    assert report['pages'][0]['pixel_suspected_missing'][0]['excerpt'] == SECOND
