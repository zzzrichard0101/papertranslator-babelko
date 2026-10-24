"""Measure OCR recall against independently supplied visible-text labels.

This audits source pixels -> Input.pdf, before translation. A completed
translation or a second OCR engine is not a ground-truth transcription.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

import pymupdf as fitz

from babelko.storage import digest


def tokens(value):
    # Repeated tildes are a known phantom at scanned column gutters. Keep them
    # in the error accounting even though ordinary punctuation is ignored.
    return re.findall(r"[a-z0-9]+|~{2,}|[{}]", value.casefold())


def compare(expected, observed):
    expected_words=tokens(expected);observed_words=tokens(observed)
    reference = Counter(expected_words)
    found = Counter(observed_words)
    hits = sum((reference & found).values())
    # LCS keeps duplicate words and catches a line that OCR serialized in the
    # wrong order, which bag-of-words recall cannot see.
    prior=[0]*(len(observed_words)+1)
    for expected_word in expected_words:
        current=[0]*(len(observed_words)+1)
        for i,observed_word in enumerate(observed_words,1):
            current[i]=prior[i-1]+1 if expected_word==observed_word else max(prior[i],current[i-1])
        prior=current
    ordered=prior[-1]
    missing = list((reference - found).elements())
    extras = list((found - reference).elements())
    return dict(reference_words=sum(reference.values()), observed_words=sum(found.values()),
                matched_words=hits, ordered_matched_words=ordered,
                recall=round(hits / sum(reference.values()), 4) if reference else None,
                ordered_recall=round(ordered / sum(reference.values()), 4) if reference else None,
                precision=round(hits / sum(found.values()), 4) if found else None,
                missing=missing, extra=extras)


def overlapping_lines(page,clip):
    lines=[(fitz.Rect(line['bbox']),''.join(s['text'] for s in line['spans']).strip())
           for block in page.get_text('dict')['blocks'] for line in block.get('lines',[])
           if ''.join(s['text'] for s in line['spans']).strip()]
    lines=[(box,text) for box,text in lines if not (box & clip).is_empty]
    issues=[]
    for i,(box,text) in enumerate(lines):
        for other,other_text in lines[i+1:]:
            overlap=box & other
            if overlap.is_empty:continue
            if (abs(box.y0-other.y0)>max(4,min(box.height,other.height)*.25) and
                overlap.height>min(box.height,other.height)*.2 and
                overlap.width>min(box.width,other.width)*.5):
                issues.append(dict(first=text[:60],second=other_text[:60],
                                   vertical_overlap=round(overlap.height,2)))
    return issues


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
            outside=[dict(text=word[4],bbox=[round(v,2) for v in word[:4]])
                     for word in derived[index].get_text('words')
                     if not derived[index].rect.contains(fitz.Rect(word[:4]))]
            regions = []
            for region in item['regions']:
                clip = fitz.Rect(region['bbox'])
                if clip.is_empty or not original[index].rect.contains(clip):
                    raise ValueError(f"Invalid source region: {clip}")
                observed = derived[index].get_text(clip=clip)
                result = compare(region['text'], observed)
                regions.append(dict(label=region['label'], bbox=region['bbox'],
                                    overlapping_lines=overlapping_lines(derived[index],clip),**result))
            pages.append(dict(page=item['page'], regions=regions,outside_page=outside))
    return dict(key=case['key'], label_provenance=case['label_provenance'],
                source_sha256=case['source_sha256'], pages=pages,
                scope='Visible source text in labeled regions only; OCR recall before translation. '
                      'Unlabeled regions and semantic/translation accuracy are not measured.')


def audit_corpus(base, labels, prepare_inputs=False):
    reports = []
    for case in labels['cases']:
        source = base / 'sources' / case['source_name']
        if digest(source)!=case['source_sha256']:
            raise ValueError(f"Source hash differs from human label: {source}")
        prepared = base / 'ocr-audit-input' / case['key'] / 'Input.pdf'
        manifest=prepared.with_suffix('.audit.json')
        from babelko import ocr
        selected=sorted({page['page']-1 for page in case['pages']})
        signature=hashlib.sha256(json.dumps([case['source_sha256'],digest(Path(ocr.__file__)),
                                             selected,'auto']).encode()).hexdigest()
        if prepare_inputs:
            prepared.parent.mkdir(parents=True,exist_ok=True)
            ocr.prepare(source,prepared,'auto',progress=lambda *_:None,selected=set(selected))
            manifest.write_text(json.dumps(dict(signature=signature,sha256=digest(prepared))),encoding='utf-8')
        if not prepared.is_file():
            raise FileNotFoundError(f"Run this audit once with --prepare: {prepared}")
        saved=json.loads(manifest.read_text(encoding='utf-8')) if manifest.is_file() else {}
        if saved.get('signature')!=signature or saved.get('sha256')!=digest(prepared):
            raise ValueError(f"OCR audit input is stale; run with --prepare: {prepared}")
        reports.append(audit_case(source, prepared, case))
    regions = [region for case in reports for page in case['pages'] for region in page['regions']]
    result = dict(cases=reports, regions=len(regions),
                  reference_words=sum(r['reference_words'] for r in regions),
                  matched_words=sum(r['matched_words'] for r in regions),
                  ordered_matched_words=sum(r['ordered_matched_words'] for r in regions),
                  failures=[dict(case=c['key'], page=p['page'], label=r['label'], missing=r['missing'])
                            for c in reports for p in c['pages'] for r in p['regions'] if r['missing']],
                  unexpected_content=[dict(case=c['key'], page=p['page'], label=r['label'], extra=r['extra'])
                                      for c in reports for p in c['pages'] for r in p['regions']
                                      if not r['reference_words'] and r['extra']],
                  outside_page=[dict(case=c['key'],page=p['page'],words=p['outside_page'])
                                for c in reports for p in c['pages'] if p['outside_page']],
                  line_overlaps=[dict(case=c['key'],page=p['page'],label=r['label'],pairs=r['overlapping_lines'])
                                 for c in reports for p in c['pages'] for r in p['regions'] if r['overlapping_lines']],
                  order_deficits=[dict(case=c['key'], page=p['page'], label=r['label'],
                                       unmatched_in_sequence=r['reference_words']-r['ordered_matched_words'])
                                  for c in reports for p in c['pages'] for r in p['regions']
                                  if r['ordered_matched_words']<r['reference_words']],
                  scope='Only manually labeled or authored-control regions; no whole-corpus OCR guarantee.')
    result['recall'] = round(result['matched_words'] / result['reference_words'], 4) if result['reference_words'] else None
    result['ordered_recall'] = round(result['ordered_matched_words'] / result['reference_words'], 4) if result['reference_words'] else None
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--labels', type=Path, default=Path(__file__).parents[1] / 'tests/fixtures/ocr_audit_labels.json')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prepare', action='store_true', help='Build isolated OCR inputs from the labeled source pages')
    args = parser.parse_args()
    result = audit_corpus(args.base, json.loads(args.labels.read_text(encoding='utf-8')),args.prepare)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: result[key] for key in ('regions', 'reference_words', 'matched_words', 'recall', 'ordered_recall', 'failures', 'order_deficits', 'unexpected_content', 'outside_page', 'line_overlaps')}, ensure_ascii=False))
