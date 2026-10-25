import importlib.util
import json
from pathlib import Path

import pymupdf as fitz
import pytest


SPEC = importlib.util.spec_from_file_location(
    'diverse_30_corpus', Path(__file__).resolve().parents[1] / 'scripts' / 'diverse_30_corpus.py')
corpus = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(corpus)


def test_download_reuses_verified_file_and_rejects_long_paper(tmp_path):
    source = tmp_path / '2401.12345.pdf'
    with fitz.open() as doc:
        doc.new_page()
        doc.new_page()
        doc.save(source)

    class NoNetwork:
        def get(self, *args, **kwargs):
            raise AssertionError('Existing checked PDF must not be fetched again')

    assert corpus.download_pdf(NoNetwork(), '2401.12345', source) == 2
    with fitz.open() as doc:
        for _ in range(31):
            doc.new_page()
        doc.save(source)
    with pytest.raises(corpus.UnsuitablePdf):
        corpus.download_pdf(NoNetwork(), '2401.12345', source)


def test_report_counts_completed_only_when_worker_says_completed(tmp_path):
    base = tmp_path / 'corpus'
    base.mkdir()
    cases = [dict(key='a', field='biology', arxiv_id='2401.00001', pages=3),
             dict(key='b', field='finance', arxiv_id='2401.00002', pages=7)]
    (base / 'manifest.json').write_text(json.dumps(dict(cases=cases)), encoding='utf-8')
    (base / 'runs').mkdir()
    job = tmp_path / 'job'
    job.mkdir()
    (base / 'runs' / 'a.json').write_text(json.dumps(dict(job=str(job), attempts=1)), encoding='utf-8')
    (job / 'state.json').write_text(json.dumps(dict(status='completed')), encoding='utf-8')
    (job / 'performance.json').write_text(json.dumps(dict(elapsed_seconds=12)), encoding='utf-8')
    report = corpus.summarize(base)
    assert (report['total'], report['completed'], report['checked_pages']) == (2, 1, 3)
    assert report['rows'][1]['status'] == 'queued'
    assert 'semantic certification' in report['limitation']


def test_previous_sources_are_excluded_by_id_and_hash(tmp_path, monkeypatch):
    monkeypatch.setattr(corpus, 'PROJECT', tmp_path)
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    previous = tmp_path / 'test_vault' / 'old' / '2412.12345'
    previous.mkdir(parents=True)
    original = previous / 'Original.pdf'
    with fitz.open() as doc:
        doc.new_page()
        doc.save(original)
    ids, hashes = corpus.previous_ids_and_hashes(tmp_path / 'test_vault' / 'new')
    assert '2412.12345' in ids
    assert corpus.digest(original) in hashes


def test_schedule_only_stops_after_every_case_is_terminal():
    rows = [dict(status='completed', attempts=1) for _ in range(29)]
    assert not corpus.finished(dict(total=30, rows=rows + [dict(status='queued', attempts=0)]))
    assert corpus.finished(dict(total=30, rows=rows + [dict(status='failed', attempts=1)]))
    assert corpus.finished(dict(total=30, rows=rows + [dict(status='partial', attempts=1)]))


def test_repeated_incomplete_documents_hold_batch(tmp_path):
    recent=[('first','partial'),('second','failed')]
    assert not corpus.hold_after_repeated_failures(tmp_path,recent)
    assert not corpus.hold_after_repeated_failures(tmp_path,recent+[('third','completed')])
    assert corpus.hold_after_repeated_failures(tmp_path,recent+[('third','partial')])
    hold=json.loads((tmp_path/'batch-hold.json').read_text(encoding='utf-8'))
    assert len(hold['recent'])==3
