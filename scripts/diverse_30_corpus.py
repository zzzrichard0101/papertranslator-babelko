"""Private, resumable 30-paper local translation benchmark.

`prepare` downloads and freezes a field-balanced corpus; `run` is safe to invoke
repeatedly from Windows Task Scheduler. Source PDFs and model responses stay in
the ignored test_vault. The report contains mechanical checks, not a claim of
independent translation accuracy.
"""
import argparse
import datetime as dt
import html
import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import psutil
import pymupdf as fitz
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from babelko.storage import digest, read, save

PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = PROJECT / 'test_vault' / 'diverse-30-20261024'
ATOM = '{http://www.w3.org/2005/Atom}'
ID_RE = re.compile(r'(?<!\d)(\d{4}\.\d{4,5})(?:v\d+)?(?!\d)')
FIELDS = [
    ('computer_vision', 'cs.CV'), ('language', 'cs.CL'),
    ('cybersecurity', 'cs.CR'), ('software_engineering', 'cs.SE'),
    ('number_theory', 'math.NT'), ('probability', 'math.PR'),
    ('astronomy', 'astro-ph.EP'), ('materials', 'cond-mat.mtrl-sci'),
    ('medical_physics', 'physics.med-ph'), ('quantum_physics', 'quant-ph'),
    ('molecular_biology', 'q-bio.MN'), ('quantitative_biology', 'q-bio.QM'),
    ('finance', 'q-fin.ST'), ('economics', 'econ.GN'),
    ('signal_processing', 'eess.SP'),
]


class UnsuitablePdf(ValueError):
    """A valid response that cannot be used in this fixed-size benchmark."""


def page_count(path):
    with fitz.open(path) as doc:
        pages = len(doc)
        if doc.needs_pass or not 2 <= pages <= 30:
            raise UnsuitablePdf('page count or encryption outside benchmark range')
        return pages


def previous_ids_and_hashes(base):
    """Exclude earlier test documents and original PDFs from both app data roots."""
    ids, hashes = set(), set()
    roots = [PROJECT / 'test_vault', Path(os.environ['LOCALAPPDATA']) / 'PaperTranslatorBabelKO',
             Path(os.environ['LOCALAPPDATA']) / 'PaperTranslator' / 'results']
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob('*.pdf'):
            if base in path.parents:
                continue
            ids.update(ID_RE.findall(str(path)))
            if path.name.lower() == 'original.pdf':
                hashes.add(digest(path))
        for path in root.rglob('state.json'):
            try:
                state = read(path)
                if state.get('source_sha256'):
                    hashes.add(state['source_sha256'])
            except (OSError, ValueError):
                continue
        for path in root.glob('*/manifest.json'):
            try:
                payload = json.dumps(read(path), ensure_ascii=False)
                ids.update(ID_RE.findall(payload))
            except (OSError, ValueError):
                continue
    return ids, hashes


def candidates(session, category):
    params = dict(search_query=f'cat:{category} AND submittedDate:[202401010000 TO 202412312359]',
                  start=0, max_results=20, sortBy='submittedDate', sortOrder='descending')
    for attempt in range(4):
        try:
            response = session.get('https://export.arxiv.org/api/query', params=params, timeout=45)
            response.raise_for_status()
            root = ET.fromstring(response.content)
            return [dict(arxiv_id=ID_RE.search(e.findtext(ATOM + 'id', '')).group(1),
                         title=' '.join(e.findtext(ATOM + 'title', '').split()),
                         published=e.findtext(ATOM + 'published', '')[:10])
                    for e in root.findall(ATOM + 'entry') if ID_RE.search(e.findtext(ATOM + 'id', ''))]
        except (requests.RequestException, ET.ParseError):
            if attempt == 3:
                raise
            time.sleep(3 * (attempt + 1))


def download_pdf(session, arxiv_id, destination):
    if destination.exists():
        return page_count(destination)
    for attempt in range(4):
        try:
            response = session.get('https://arxiv.org/pdf/' + arxiv_id, timeout=90)
            response.raise_for_status()
            if not response.content.startswith(b'%PDF-') or len(response.content) > 30 * 1024**2:
                raise UnsuitablePdf('invalid or oversized PDF')
            temp = destination.with_suffix('.download')
            temp.write_bytes(response.content)
            try:
                pages = page_count(temp)
                temp.replace(destination)
                return pages
            finally:
                temp.unlink(missing_ok=True)
        except UnsuitablePdf:
            raise
        except (requests.RequestException, ValueError, fitz.FileDataError):
            if attempt == 3:
                raise
            time.sleep(3 * (attempt + 1))


def prepare(base):
    manifest = base / 'manifest.json'
    if manifest.exists():
        cases = read(manifest)['cases']
        if len(cases) == 30 and all(Path(c['source']).is_file() and digest(c['source']) == c['sha256'] for c in cases):
            return cases
        raise RuntimeError('Frozen corpus incomplete or changed; inspect before proceeding')
    sources = base / 'sources'
    sources.mkdir(parents=True, exist_ok=True)
    old_ids, old_hashes = previous_ids_and_hashes(base)
    session = requests.Session()
    session.headers['User-Agent'] = 'PaperTranslator-BabelKO local research benchmark/0.1 (academic testing)'
    cases, used = [], set()
    for field, category in FIELDS:
        selected = 0
        for candidate in candidates(session, category):
            arxiv_id = candidate['arxiv_id']
            if arxiv_id in old_ids or arxiv_id in used:
                continue
            path = sources / (arxiv_id + '.pdf')
            try:
                pages = download_pdf(session, arxiv_id, path)
                sha = digest(path)
                if sha in old_hashes:
                    path.unlink()
                    continue
            except (requests.RequestException, ValueError, fitz.FileDataError) as exc:
                print(f'skip {arxiv_id}: {type(exc).__name__}: {exc}', flush=True)
                continue
            cases.append(dict(key=f'{field}-{selected + 1}', field=field, category=category,
                              **candidate, source=str(path), url='https://arxiv.org/abs/' + arxiv_id,
                              pdf_url='https://arxiv.org/pdf/' + arxiv_id, sha256=sha, pages=pages))
            used.add(arxiv_id)
            selected += 1
            print(f'{len(cases)}/30 {field}: {arxiv_id} ({pages} pages)', flush=True)
            if selected == 2:
                break
            time.sleep(3)
        if selected != 2:
            raise RuntimeError(f'Only {selected} suitable papers found for {category}; no benchmark scheduled')
        time.sleep(3)
    save(manifest, dict(created_at=dt.datetime.now(dt.timezone.utc).isoformat(),
                        scope='30 complete public papers, two per field; local hybrid inference; no human semantic reference',
                        excluded_existing_ids=len(old_ids), excluded_existing_hashes=len(old_hashes), cases=cases))
    return cases


def app_busy(home):
    lock = home / 'worker.lock'
    if not lock.exists():
        return False
    try:
        owner = read(lock)
        process = psutil.Process(owner['pid'])
        return process.is_running() and abs(process.create_time() - owner['created']) < 1
    except (OSError, ValueError, KeyError, psutil.Error):
        # Let the worker's own checked stale-lock recovery decide.
        return False


def another_model_busy():
    try:
        return any((process.info['name'] or '').lower().startswith('llama-server')
                   for process in psutil.process_iter(['name']))
    except psutil.Error:
        return True


def summarize(base):
    rows = []
    for case in read(base / 'manifest.json')['cases']:
        record_path = base / 'runs' / (case['key'] + '.json')
        record = read(record_path) if record_path.exists() else {}
        job = Path(record['job']) if record.get('job') else None
        state = read(job / 'state.json') if job and (job / 'state.json').exists() else {}
        output = Path(state['output']) if state.get('output') else None
        quality = read(output / 'Quality.json') if output and (output / 'Quality.json').exists() else {}
        performance = read(job / 'performance.json') if job and (job / 'performance.json').exists() else {}
        checks = quality.get('checks', {})
        status = ('paused' if record.get('status') == 'paused' and state.get('status') == 'cancelled'
                  else state.get('status', 'queued'))
        rows.append(dict(key=case['key'], field=case['field'], arxiv_id=case['arxiv_id'],
                         source_pages=case['pages'], status=status,
                         current_stage=state.get('stage'), progress=state.get('progress'),
                         attempts=record.get('attempts', 0),
                         elapsed_seconds=performance.get('elapsed_seconds'),
                         seconds_per_page=(round(performance['elapsed_seconds'] / case['pages'], 2)
                                           if performance.get('elapsed_seconds') else None),
                         checks=checks.get('status'), issue_codes=[x.get('code') for x in checks.get('issues', [])],
                         tracking=quality.get('translation_tracking', {}).get('status'),
                         untranslated_units=quality.get('translation_tracking', {}).get('units_with_no_output'),
                         meaning_assurance=quality.get('meaning_assurance', {}).get('status'),
                         rendered_prose=quality.get('rendered_prose', {}).get('status'),
                         figures=quality.get('figures', {}).get('status'),
                         ocr_pages=len(state.get('ocr_pages', [])),
                         error=state.get('error'), output=str(output) if output else None))
    completed = [r for r in rows if r['status'] == 'completed']
    seconds = sum(r['elapsed_seconds'] or 0 for r in rows)
    issue_counts = {}
    for row in rows:
        for code in row['issue_codes']:
            issue_counts[code] = issue_counts.get(code, 0) + 1
    report = dict(updated_at=dt.datetime.now(dt.timezone.utc).isoformat(), total=len(rows),
                  completed=len(completed), partial=sum(r['status'] == 'partial' for r in rows),
                  failed=sum(r['status'] == 'failed' for r in rows),
                  issue_counts=issue_counts,
                  batch_hold=read(base / 'batch-hold.json') if (base / 'batch-hold.json').exists() else None,
                  checked_pages=sum(r['source_pages'] for r in completed),
                  qa_passed=sum(r['checks'] == 'passed' and r['tracking'] == 'passed'
                                and r['meaning_assurance'] == 'passed' and r['rendered_prose'] == 'passed'
                                for r in completed),
                  total_untranslated_units=sum(r['untranslated_units'] or 0 for r in rows),
                  summed_worker_seconds=round(seconds, 2), rows=rows,
                  limitation='Mechanical coverage/layout checks only; no independent reference translation or semantic certification.')
    save(base / 'report.json', report)
    cells = []
    for row in rows:
        link = (f'<a href="{html.escape((Path(row["output"]) / "Bilingual.pdf").as_uri(), quote=True)}">결과 PDF</a>'
                if row['output'] and (Path(row['output']) / 'Bilingual.pdf').exists() else '')
        values = [row['field'].replace('_', ' '), row['arxiv_id'],
                  f'{row["status"]} {round(row["progress"] or 0)}%',
                  str(row['source_pages']), str(row['elapsed_seconds'] or '—'),
                  str(row['checks'] or '—'), ', '.join(row['issue_codes']), link]
        cells.append('<tr>' + ''.join(f'<td>{v if i == 7 else html.escape(v)}</td>'
                                        for i, v in enumerate(values)) + '</tr>')
    hold = ('<p class="hold">반복된 검증 실패로 자동 번역을 일시 중지했습니다. '
            '저장된 작업은 유지됩니다.</p>' if report['batch_hold'] else '')
    issue_names = dict(translation_failed='번역 조각 미완료', rendered_prose_missing='PDF 표시 누락',
                       figure_legend_incomplete='그림 설명 미완료')
    issue_summary = ' · '.join(f'{issue_names.get(code, code)} {count}편'
                             for code, count in sorted(issue_counts.items())) or '현재 기록된 검사 문제 없음'
    page = '''<!doctype html><html lang="ko"><meta charset="utf-8"><meta http-equiv="refresh" content="120">
<title>BabelKO 30편 평가</title><style>
body{{font:15px/1.6 system-ui,sans-serif;max-width:1300px;margin:40px auto;padding:0 22px;color:#243347;background:#f7f9fc}}
h1{{font-size:30px;margin-bottom:6px}}.summary{{font-size:18px;margin:0 0 24px}}
table{{border-collapse:collapse;width:100%;background:white}}th,td{{padding:9px 12px;text-align:left;border-bottom:1px solid #e3e9ef}}
th{{background:#eaf1f5;position:sticky;top:0}}tr:hover{{background:#f2f8fa}}.note{{color:#5c6977}}
.hold{{padding:12px 16px;background:#fff1df;color:#713b09;border-radius:8px}}
</style><h1>다양한 분야 논문 30편 평가</h1>
<p class="summary">완료 <b>{completed}/30</b> · QA 통과 <b>{qa_passed}</b> · 일부 완료 <b>{partial}</b> · 실패 <b>{failed}</b> · 검증된 쪽 <b>{pages}</b></p>
{hold}
<p class="note">검사 문제: {issues}</p>
<p class="note">로컬 모델로 순차 처리합니다. 이 페이지는 2분마다 새로고침됩니다. QA는 누락·배치 등의 자동 점검이며 번역 의미의 완전성을 보증하지 않습니다.</p>
<table><thead><tr><th>분야</th><th>논문 ID</th><th>진행</th><th>쪽</th><th>초</th><th>QA</th><th>문제 코드</th><th>파일</th></tr></thead><tbody>{rows}</tbody></table></html>'''.format(
        completed=report['completed'], qa_passed=report['qa_passed'], partial=report['partial'],
        failed=report['failed'], pages=report['checked_pages'], hold=hold,
        issues=html.escape(issue_summary), rows=''.join(cells))
    (base / 'Report.html').write_text(page, encoding='utf-8')
    return report


def finished(report):
    return report['total'] == 30 and all(
        row['status'] in {'completed', 'failed', 'partial'}
        for row in report['rows'])


def stop_completed_schedule(base, report):
    if not finished(report) or base.resolve() != DEFAULT_BASE.resolve():
        return
    command = ("'PaperTranslator-BabelKO-Diverse30',"
               "'PaperTranslator-BabelKO-Diverse30-Report' | ForEach-Object "
               "{ Get-ScheduledTask -TaskName $_ -ErrorAction SilentlyContinue "
               "| Disable-ScheduledTask | Out-Null }")
    subprocess.run(['powershell', '-NoProfile', '-Command', command], check=True,
                   capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    print('Benchmark finished; both local scheduled tasks disabled.', flush=True)


def hold_after_repeated_failures(base, recent):
    """Avoid burning hours on a newly broken pipeline across many PDFs."""
    if len(recent) < 3 or any(status == 'completed' for _, status in recent[-3:]):
        return False
    save(base / 'batch-hold.json', dict(reason='three consecutive documents did not pass QA',
                                       recent=recent[-3:], created_at=dt.datetime.now(dt.timezone.utc).isoformat()))
    if base.resolve() == DEFAULT_BASE.resolve():
        subprocess.run(['powershell', '-NoProfile', '-Command',
                        "Disable-ScheduledTask -TaskName 'PaperTranslator-BabelKO-Diverse30' | Out-Null"],
                       check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    print('Three consecutive incomplete documents; automatic batch paused for diagnosis.', flush=True)
    return True


def run(base, once=False, case_key=None):
    from babelko.pipeline import create

    manifest = read(base / 'manifest.json')
    if len(manifest['cases']) != 30:
        raise RuntimeError('Need a frozen 30-paper manifest')
    if case_key and case_key not in {case['key'] for case in manifest['cases']}:
        raise ValueError('Unknown benchmark case: ' + case_key)
    if (base / 'batch-hold.json').exists():
        print('Batch is held for quality diagnosis; resume explicitly after a fix.', flush=True)
        return
    home = base / 'home'
    home.mkdir(exist_ok=True)
    source_assets = Path(os.environ['LOCALAPPDATA']) / 'PaperTranslatorBabelKO' / 'assets'
    if not source_assets.is_dir():
        raise RuntimeError('Local model/layout assets are not installed')
    link = home / 'assets'
    if not link.exists():
        command = "New-Item -ItemType Junction -Path '" + str(link).replace("'", "''") + "' -Target '" + str(source_assets).replace("'", "''") + "' | Out-Null"
        subprocess.run(['powershell', '-NoProfile', '-Command', command], check=True,
                       capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    os.environ['BABELKO_HOME'] = str(home)
    output = base / 'results'
    output.mkdir(exist_ok=True)
    records = base / 'runs'
    records.mkdir(exist_ok=True)
    recent = []
    for case in manifest['cases']:
        if case_key and case['key'] != case_key:
            continue
        record_path = records / (case['key'] + '.json')
        record = read(record_path) if record_path.exists() else {}
        # A second full pass without a changed mechanism wastes GPU hours.
        # Finish first-pass coverage; explicit --case selects a known failure
        # for a checkpointed recheck after a targeted fix.
        if record.get('status') in {'completed', 'failed', 'partial'} and not case_key:
            continue
        if (app_busy(home) or app_busy(Path(os.environ['LOCALAPPDATA']) / 'PaperTranslatorBabelKO')
                or another_model_busy()):
            print('Another app translation is active; scheduled retry will continue later.', flush=True)
            break
        if digest(case['source']) != case['sha256']:
            raise RuntimeError('Source PDF changed: ' + case['key'])
        job = Path(record['job']) if record.get('job') else create(case['source'], output, mode='hybrid')
        attempts = record.get('attempts', 0) + 1
        save(record_path, dict(key=case['key'], job=str(job), attempts=attempts,
                               status='running', started_at=dt.datetime.now(dt.timezone.utc).isoformat()))
        print(f'run {case["key"]} attempt {attempts}', flush=True)
        with (records / (case['key'] + '.log')).open('a', encoding='utf-8') as log:
            process = subprocess.run([sys.executable, '-u', '-m', 'babelko.worker', str(job)], cwd=PROJECT,
                                     env={**os.environ, 'PYTHONIOENCODING': 'utf-8'},
                                     stdout=log, stderr=subprocess.STDOUT,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
        state = read(job / 'state.json')
        save(record_path, dict(key=case['key'], job=str(job), attempts=attempts,
                               status=state['status'], returncode=process.returncode,
                               ended_at=dt.datetime.now(dt.timezone.utc).isoformat()))
        report = summarize(base)
        print(f'{case["key"]}: {state["status"]}; completed {report["completed"]}/30', flush=True)
        recent.append((case['key'], state['status']))
        if once:
            break
        if hold_after_repeated_failures(base, recent):
            break
    report = summarize(base)
    stop_completed_schedule(base, report)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'run', 'report'])
    parser.add_argument('--base', type=Path, default=DEFAULT_BASE)
    parser.add_argument('--once', action='store_true', help='Process at most one pending paper')
    parser.add_argument('--case', help='Recheck one named paper without launching the batch')
    args = parser.parse_args()
    base = args.base.resolve()
    base.mkdir(parents=True, exist_ok=True)
    if args.action == 'prepare':
        prepare(base)
    elif args.action == 'report':
        print(json.dumps(summarize(base), ensure_ascii=False, indent=2))
    else:
        log = base / 'scheduler.log'
        with log.open('a', encoding='utf-8') as stream:
            from contextlib import redirect_stderr, redirect_stdout
            with redirect_stdout(stream), redirect_stderr(stream):
                print('scheduler start', dt.datetime.now(dt.timezone.utc).isoformat(), flush=True)
                run(base, args.once, args.case)
                print('scheduler finish', dt.datetime.now(dt.timezone.utc).isoformat(), flush=True)


if __name__ == '__main__':
    main()
