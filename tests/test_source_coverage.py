from types import SimpleNamespace as Obj

import pymupdf
import pytest

from babelko.source_coverage import (evidence_export_valid, identifier_output_status,
                                     english_words, inspect, math_prose_match, source_lines,
                                     source_prose_gate, standalone_identifier)
from babelko.storage import digest


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
    gate = source_prose_gate(report)
    assert gate['status'] == 'failed'
    assert gate['issues'][0]['code'] == 'native_line_missing'
    assert report['pages'][0]['suspected_missing'][0]['line_id'] in {
        row['id'] for row in report['evidence_rows'] if row.get('resolution') == 'suspected_missing'}
    assert len([row for row in report['evidence_rows'] if row['extractor'] == 'il_paragraph']) == 1
    assert len([row for row in report['evidence_rows'] if row['extractor'] == 'native']) == 2
    assert report['evidence_rows'] == inspect(pdf, docs)['evidence_rows']
    assert docs.page[0].pdf_paragraph[0].unicode == FIRST


def test_complete_source_and_rich_style_text_do_not_trigger_missing_line(tmp_path):
    pdf = tmp_path / 'input.pdf'
    docs = document(pdf, "<style id='1'>" + FIRST + '</style>', SECOND)
    report = inspect(pdf, docs)
    assert report['suspected_missing_lines'] == 0
    assert source_prose_gate(report)['status'] == 'passed'


def test_lost_word_spaces_preserve_exact_character_order(tmp_path):
    pdf = tmp_path / 'input.pdf'
    docs = document(pdf, FIRST, SECOND.replace(' ', ''))
    report = inspect(pdf, docs)
    assert report['suspected_missing_lines'] == 0
    native = [row for row in report['evidence_rows'] if row['extractor'] == 'native']
    assert native[1]['resolution'] == 'matched'
    assert native[1]['compact_sequence_match']
    assert native[1]['il_paragraph_ids']


def test_no_native_text_layer_is_uninformative_not_certified(tmp_path):
    pdf = tmp_path / 'scan.pdf'
    with pymupdf.open() as source:
        source.new_page(width=600, height=800)
        source.save(pdf)
    report = inspect(pdf, Obj(page=[Obj(page_number=0, pdf_paragraph=[])]))
    assert report['candidate_lines'] == 0
    assert report['status'] == 'diagnostic'
    assert report['pages_without_prose_evidence'] == [1]
    assert source_prose_gate(report)['unchecked_pages'] == [1]
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
    assert report['corroborated_suspected_missing_lines'] == 1
    missing = report['pages'][0]['suspected_missing'][0]['line_id']
    ledger = {row['id']: row for row in report['evidence_rows']}
    assert ledger[missing]['corroborated_by']
    assert ledger[missing]['il_paragraph_ids'] == []


def test_same_ocr_words_in_another_location_do_not_corroborate_omission(tmp_path):
    pdf = tmp_path / 'input.pdf'
    docs = document(pdf, FIRST)
    rows = {0: [dict(text=SECOND, bbox=[45, 300, 520, 320], score=.99)]}
    report = inspect(pdf, docs, pixel_rows=rows)
    assert report['suspected_missing_lines'] == 1
    assert report['pixel_suspected_missing_rows'] == 1
    assert report['corroborated_suspected_missing_lines'] == 0


def test_empty_page_does_not_link_evidence_from_previous_page(tmp_path):
    pdf = tmp_path / 'input.pdf'
    with pymupdf.open() as source:
        first = source.new_page(width=600, height=800)
        first.insert_text((45, 90), FIRST, fontsize=11)
        source.new_page(width=600, height=800)
        source.save(pdf)
    docs = Obj(page=[Obj(page_number=0, pdf_paragraph=[Obj(unicode=FIRST)]),
                     Obj(page_number=1, pdf_paragraph=[])])
    report = inspect(pdf, docs)
    assert report['pages'][1]['source_page'] == 2
    assert report['pages'][1]['suspected_missing'] == []
    assert [row['source_page'] for row in report['evidence_rows']] == [1, 1]


def test_declared_evidence_requires_an_intact_export(tmp_path):
    coverage = dict(evidence_ledger=dict(status='available', sha256='missing'))
    assert not evidence_export_valid(tmp_path, coverage)
    path = tmp_path / 'SourceEvidence.json'
    path.write_text('{"rows":[]}', encoding='utf-8')
    coverage['evidence_ledger']['sha256'] = digest(path)
    assert evidence_export_valid(tmp_path, coverage)
    path.write_text('{"rows":[1]}', encoding='utf-8')
    assert not evidence_export_valid(tmp_path, coverage)
    assert evidence_export_valid(tmp_path, {})  # Older reports never declared this artifact.
    assert source_prose_gate({'status': 'unavailable'})['status'] == 'failed'


def test_standalone_doi_is_preserved_and_checked_in_final_page():
    source = 'https://doi.org/10.5281/zenodo.18063244 .'
    assert standalone_identifier(source) == 'https://doi.org/10.5281/zenodo.18063244'
    assert standalone_identifier('For details see ' + source) is None
    coverage = {'pages': [dict(source_page=3, preserved_identifier_rows=[
        dict(line_id='doi-row', identifier='https://doi.org/10.5281/zenodo.18063244')])]}
    assert identifier_output_status(coverage, [2], ['한글 https://doi.org/10.5281/\nzenodo.18063244'])['status'] == 'passed'
    missing = identifier_output_status(coverage, [2], ['한글 본문'])
    assert missing['status'] == 'failed'
    assert missing['issues'] == [dict(source_page=3, line_id='doi-row')]


def test_identifier_output_accepts_pdf_hyphen_and_zero_width_variants_only():
    coverage = {'pages': [dict(source_page=1, preserved_identifier_rows=[
        dict(line_id='doi', identifier='https://\u200bdoi.\u200borg/\u200b10.3847/1538-4357/acc6cc')])]}
    rendered = 'https://doi.org/10.3847/1538‑4357/acc6cc'
    assert identifier_output_status(coverage, [0], [rendered])['status'] == 'passed'
    assert identifier_output_status(coverage, [0],
        [rendered.replace('acc6cc', 'acc6cd')])['status'] == 'failed'


def test_math_prose_survives_formula_placeholder_reformatting():
    source = ('The function (1 − x) is not integrable for β = −1 and hence the measure '
              'converges weakly to the uniform distribution.')
    parsed = ('Although the function {v1} is not integrable for {v2} and hence the '
              'measure converges weakly to the uniform distribution.')
    assert math_prose_match(source, [('paragraph', parsed)]) == [(1.0, 'paragraph')]
    assert not math_prose_match(source, [('paragraph', 'The measure converges weakly.')])
    assert 'integrable' in english_words('∥x∥<1 is not integrable for β>1')
