"""Read-only replay of saved spatial ledgers over a labeled PDF corpus.

The manifest maps job IDs to "clean" or "fault". These labels must come from
independent knowledge of the output, not from RegionLedger's own verdict.
No source text, PDF paths, or model responses are included in the report.
"""
import argparse
import collections
import copy
import hashlib
import json
from pathlib import Path

import pymupdf as fitz

from babelko.region_ledger import REVISION,RegionLedger
from babelko.storage import digest,read,save


def layout_signature(source,selected,ocr_pages):
    with fitz.open(source) as pdf:
        pages=[(round(pdf[i].rect.width),round(pdf[i].rect.height),pdf[i].rotation)
            for i in selected]
    payload=dict(pages=pages,ocr=sorted(set(ocr_pages)&set(selected)))
    return hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()[:16]


def audit_job(job,label=None):
    state=read(job/'state.json')
    ledger_data=read(job/'region-ledger.json')
    source=job/'Original.pdf'
    output=Path(state['output'])/'Korean.pdf' if state.get('output') else None
    if not source.is_file() or output is None or not output.is_file():
        raise FileNotFoundError('saved source or Korean PDF missing')
    model_id=state.get('snapshot',{}).get('model',{}).get('id','')
    synthetic=model_id.startswith('synthetic-')
    if isinstance(label,dict):
        if digest(output)!=label.get('korean_sha256'):
            raise ValueError('reviewed PDF hash mismatch')
        label=label['label']
    elif label is not None and not synthetic:
        raise ValueError('real PDF labels require korean_sha256')
    # Early ledger revisions did not store the source hash. The job's copied
    # original is still independently checked against its creation snapshot.
    if (digest(source)!=state['source_sha256'] or
            ledger_data.get('source_sha256') not in (None,state['source_sha256'])):
        raise ValueError('source hash mismatch')
    quality_path=output.parent/'Quality.json'
    quality=read(quality_path) if quality_path.is_file() else {}
    ledger=RegionLedger(job)
    ledger.rows=copy.deepcopy(ledger_data['regions'])
    ledger.unknown=copy.deepcopy(ledger_data.get('unmapped',[]))
    report=ledger.inspect(output,state['selected'],source,
        quality.get('restored_original_index_pages',[]),save_report=False)
    codes=collections.Counter(code for issue in report['issues']
        for code in issue.get('codes',[issue.get('code','unknown')]))
    return dict(job_id=job.name,label=label or 'unlabeled',pipeline_status=state.get('status'),
        source_sha256=state['source_sha256'],
        captured_revision=ledger_data.get('revision'),eligible=ledger_data.get('revision')==REVISION,
        synthetic=synthetic,
        layout_signature=layout_signature(source,state['selected'],state.get('ocr_pages',[])),
        source_pages=len(state['selected']),checked_regions=report['checked_regions'],
        verdict=report['status'],issue_codes=dict(sorted(codes.items())))


def audit_corpus(root,labels=None):
    labels=labels or {}
    rows=[];skipped=[]
    for ledger_path in sorted(Path(root).rglob('region-ledger.json')):
        job=ledger_path.parent
        try:
            rows.append(audit_job(job,labels.get(job.name)))
        except (FileNotFoundError,KeyError,ValueError,RuntimeError,fitz.FileDataError) as error:
            skipped.append(dict(job_id=job.name,reason=type(error).__name__))
    eligible=[row for row in rows if row['eligible']]
    ineligible_clean=[row['job_id'] for row in eligible
        if row['label']=='clean' and row['pipeline_status']!='completed']
    clean=[row for row in eligible if row['label']=='clean' and row['pipeline_status']=='completed']
    faulty=[row for row in eligible if row['label']=='fault']
    real_clean=[row for row in clean if not row['synthetic']]
    false_positives=[row['job_id'] for row in clean if row['verdict']=='failed']
    missed_faults=[row['job_id'] for row in faulty if row['verdict']=='passed']
    distinct_real_sources=len({row['source_sha256'] for row in real_clean})
    distinct_real_layouts=len({row['layout_signature'] for row in real_clean})
    ready=(distinct_real_sources>=20 and distinct_real_layouts>=6 and
        not false_positives and not missed_faults and len(faulty)>=1)
    return dict(revision=REVISION,jobs=len(rows),eligible_jobs=len(eligible),
        historical_revision_jobs=len(rows)-len(eligible),skipped=skipped,
        verdicts=dict(collections.Counter(row['verdict'] for row in rows)),
        labeled_clean=len(clean),labeled_fault=len(faulty),
        ineligible_clean_jobs=ineligible_clean,
        real_clean_sources=distinct_real_sources,real_clean_layouts=distinct_real_layouts,
        false_positive_jobs=false_positives,missed_fault_jobs=missed_faults,
        promotion_evidence_ready=ready,
        criteria='At least 20 distinct real clean source PDFs, 6 layout signatures, 1 labeled fault, no false positives or missed faults. Labels must be independent of the checker.',
        jobs_detail=rows)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path,help='Directory containing saved job folders')
    parser.add_argument('--manifest',type=Path,help='JSON object: job ID -> clean or fault')
    parser.add_argument('--output',type=Path,help='Write a text-free JSON summary')
    args=parser.parse_args()
    labels=read(args.manifest) if args.manifest else {}
    if (not isinstance(labels,dict) or any(
            (value not in {'clean','fault'} if isinstance(value,str) else
                not isinstance(value,dict) or value.get('label') not in {'clean','fault'}
                or not isinstance(value.get('korean_sha256'),str))
            for value in labels.values())):
        parser.error('manifest values must be clean/fault or {label, korean_sha256}')
    result=audit_corpus(args.root,labels)
    if args.output:save(args.output,result)
    print(json.dumps({key:value for key,value in result.items() if key!='jobs_detail'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
