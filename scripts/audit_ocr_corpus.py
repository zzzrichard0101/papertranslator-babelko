"""Measure OCR recall against independently supplied visible-text labels.

This audits source pixels -> Input.pdf, before translation. A completed
translation or a second OCR engine is not a ground-truth transcription.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import re

import pymupdf as fitz

from babelko.storage import digest


def tokens(value):
    # Repeated tildes are a known phantom at scanned column gutters. Keep them
    # in the error accounting even though ordinary punctuation is ignored.
    return re.findall(r"[a-z0-9]+|~{2,}", value.casefold())


def compare(expected, observed):
    reference = Counter(tokens(expected))
    found = Counter(tokens(observed))
    hits = sum((reference & found).values())
    missing = list((reference - found).elements())
    extras = list((found - reference).elements())
    return dict(reference_words=sum(reference.values()), observed_words=sum(found.values()),
                matched_words=hits, recall=round(hits / sum(reference.values()), 4) if reference else None,
                precision=round(hits / sum(found.values()), 4) if found else None,
                missing=missing, extra=extras)


def audit_case(source, prepared, case):
    if digest(source) != case['source_sha256']:
        raise ValueError(f"Source hash differs from human label: {source}")
    with fitz.open(source) as original, fitz.open(prepared) as derived:
        if len(original) != len(derived):
            raise ValueError(f"OCR input page count differs: {prepared}")
        pages = []
        for item in case['pages']:
            index = item['page'] - 1
            if index < 0 or index >= len(original):
                raise ValueError(f"Labeled page outside PDF: {item['page']}")
            regions = []
            for region in item['regions']:
                clip = fitz.Rect(region['bbox'])
                if clip.is_empty or not original[index].rect.contains(clip):
                    raise ValueError(f"Invalid source region: {clip}")
                observed = derived[index].get_text(clip=clip)
                result = compare(region['text'], observed)
                regions.append(dict(label=region['label'], bbox=region['bbox'], **result))
            pages.append(dict(page=item['page'], regions=regions))
    return dict(key=case['key'], label_provenance=case['label_provenance'],
                source_sha256=case['source_sha256'], pages=pages,
                scope='Visible source text in labeled regions only; OCR recall before translation. '
                      'Unlabeled regions and semantic/translation accuracy are not measured.')


def audit_corpus(base, labels):
    reports = []
    for case in labels['cases']:
        source = base / 'sources' / case['source_name']
        run = json.loads((base / 'runs' / f"{case['key']}.json").read_text(encoding='utf-8'))
        prepared = Path(run['job']) / 'Input.pdf'
        reports.append(audit_case(source, prepared, case))
    regions = [region for case in reports for page in case['pages'] for region in page['regions']]
    result = dict(cases=reports, regions=len(regions),
                  reference_words=sum(r['reference_words'] for r in regions),
                  matched_words=sum(r['matched_words'] for r in regions),
                  failures=[dict(case=c['key'], page=p['page'], label=r['label'], missing=r['missing'])
                            for c in reports for p in c['pages'] for r in p['regions'] if r['missing']],
                  scope='Only manually labeled or authored-control regions; no whole-corpus OCR guarantee.')
    result['recall'] = round(result['matched_words'] / result['reference_words'], 4) if result['reference_words'] else None
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--labels', type=Path, default=Path(__file__).parents[1] / 'tests/fixtures/ocr_audit_labels.json')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit_corpus(args.base, json.loads(args.labels.read_text(encoding='utf-8')))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: result[key] for key in ('regions', 'reference_words', 'matched_words', 'recall', 'failures')}, ensure_ascii=False))
