"""Reinspect saved, source-bound IL without loading a translation model.

Only writes the local test corpus report; it does not change job checkpoints or
published translation outputs. Human labels must be added separately before
any diagnostic threshold becomes a completion gate.
"""

import argparse
import json
from pathlib import Path

from babelko.layout_cache import LayoutCache
from babelko.provenance import build as build_provenance
from babelko.source_coverage import evidence_tokens, inspect
from babelko.storage import read, save


def calibrate(base, limit=None, only_jobs=None, provenance=False):
    base = Path(base)
    jobs = sorted((base / 'home' / 'jobs').iterdir())
    if only_jobs is not None:
        jobs = [job for job in jobs if job.name in only_jobs]
    results = []
    for folder in jobs[:limit]:
        manifest = folder / 'layout-cache' / 'manifest.json'
        source = folder / ('Layout-input.pdf' if (folder / 'Layout-input.pdf').is_file() else 'Input.pdf')
        if not manifest.is_file() or not source.is_file():
            continue
        cached = read(manifest)
        docs = LayoutCache(folder).load(cached['identity'])
        if docs is None:
            results.append(dict(job=folder.name, status='cache_unavailable'))
            continue
        report = inspect(source, docs)
        evidence_rows = report.pop('evidence_rows')
        evidence = {row['id']: row for row in evidence_rows}
        by_page = {}
        for row in evidence.values():
            if row['extractor'] == 'il_paragraph':
                by_page.setdefault(row['source_page'], []).append(row)
        suspects = []
        for page in report['pages']:
            for row in page['suspected_missing']:
                source_row = evidence[row['line_id']]
                nearest = [evidence[key]['excerpt'] for key in source_row['il_paragraph_ids']
                           if key in evidence]
                terms = set(evidence_tokens(source_row['text']))
                candidates = []
                for paragraph in by_page.get(page['source_page'], []):
                    score = len(terms & set(evidence_tokens(paragraph['text'])))/len(terms)
                    if score:
                        candidates.append(dict(score=round(score, 3), excerpt=paragraph['excerpt']))
                candidates.sort(key=lambda item: item['score'], reverse=True)
                suspects.append(dict(source_page=page['source_page'], line_id=row['line_id'],
                                     box=row['box'], excerpt=row['excerpt'],
                                     lexical=row['lexical'], sequence=row['sequence'],
                                     linked_il=nearest, best_il=candidates[:3]))
        result = dict(job=folder.name, status='inspected',
                            source_sha256=report['input_sha256'],
                            pages=report['inspected_pages'],
                            candidate_lines=report['candidate_lines'],
                            weak_matches=report['weak_match_lines'],
                            suspects=suspects)
        if provenance:
            state = read(folder / 'state.json')
            output = Path(state.get('output') or '')
            quality_path = output / 'Quality.json'
            tracker = folder / 'intermediate' / 'translate_tracking.json'
            if quality_path.is_file() and tracker.is_file():
                local = base / 'calibration-evidence'
                local.mkdir(exist_ok=True)
                evidence_path = local / (folder.name + '.json')
                save(evidence_path, dict(input_sha256=report['input_sha256'], rows=evidence_rows))
                quality = read(quality_path)
                linked = build_provenance(evidence_path, tracker, state['selected'],
                                          quality.get('rendered_prose'))
                result['provenance'] = {key: linked[key] for key in
                                        ('tracked_units', 'matched_units', 'unlinked_units', 'missing_rendered_units')}
                result['rendered_missing'] = quality.get('rendered_prose', {}).get('missing', [])
        results.append(result)
    return dict(revision='source-coverage-calibration-1',
                inspected_jobs=sum(row['status']=='inspected' for row in results),
                candidate_lines=sum(row.get('candidate_lines', 0) for row in results),
                suspected_missing_lines=sum(len(row.get('suspects', [])) for row in results),
                results=results,
                scope='Saved IL versus native PDF layer; not a human-labeled truth set')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', type=Path,
                        default=Path(__file__).resolve().parents[1] / 'test_vault' / 'diverse-30-20261024')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--only-previous-suspects', action='store_true')
    parser.add_argument('--only-rendered-missing', action='store_true')
    parser.add_argument('--provenance', action='store_true')
    args = parser.parse_args()
    previous = args.base / 'SourceCoverageCalibration.json'
    only_jobs = ({row['job'] for row in read(previous)['results'] if row.get('suspects')}
                 if args.only_previous_suspects and previous.is_file() else None)
    if args.only_rendered_missing:
        only_jobs = set()
        for job in (args.base / 'home' / 'jobs').iterdir():
            state = read(job / 'state.json')
            quality_path = Path(state.get('output') or '') / 'Quality.json'
            if quality_path.is_file() and read(quality_path).get('rendered_prose', {}).get('status') == 'failed':
                only_jobs.add(job.name)
    report = calibrate(args.base, args.limit, only_jobs, args.provenance)
    target = args.base / 'SourceCoverageCalibration.json'
    save(target, report)
    print(json.dumps(dict(output=str(target), inspected_jobs=report['inspected_jobs'],
                          candidate_lines=report['candidate_lines'],
                          suspected_missing_lines=report['suspected_missing_lines'])))
