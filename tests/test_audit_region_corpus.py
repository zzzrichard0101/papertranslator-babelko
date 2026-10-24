import hashlib

import pymupdf as fitz

from scripts.audit_region_corpus import audit_corpus
from babelko.region_ledger import REVISION
from babelko.storage import digest,save


def saved_job(root,name,move=False):
    job=root/name
    job.mkdir()
    source=job/'Original.pdf'
    output=root/(name+'-output')
    output.mkdir()
    with fitz.open() as pdf:
        pdf.new_page(width=300,height=400).insert_text((50,80),'12')
        pdf.save(source)
    with fitz.open(source) as pdf:
        chars=[char for block in pdf[0].get_text('rawdict')['blocks']
            for line in block.get('lines',[]) for span in line.get('spans',[])
            for char in span.get('chars',[])]
    if move:
        with fitz.open() as pdf:
            pdf.new_page(width=300,height=400).insert_text((150,80),'12')
            pdf.save(output/'Korean.pdf')
    else:
        (output/'Korean.pdf').write_bytes(source.read_bytes())
    sha=digest(source)
    glyphs=[dict(text=c['c'],box=[c['bbox'][0],400-c['bbox'][3],
        c['bbox'][2],400-c['bbox'][1]]) for c in chars]
    row=dict(id=hashlib.sha256(name.encode()).hexdigest(),source_page=1,
        source_box=[45,310,75,335],role='table',source='12',policy='translate',
        inputs=['12'],record_keys=['record'],target='12',glyphs=glyphs)
    save(job/'state.json',dict(source_sha256=sha,selected=[0],ocr_pages=[],
        status='partial' if move else 'completed',
        output=str(output),snapshot=dict(model=dict(id='real-model'))))
    save(job/'region-ledger.json',dict(revision=REVISION,source_sha256=sha,regions=[row],unmapped=[]))
    return job


def test_labeled_corpus_replays_without_touching_saved_jobs(tmp_path):
    clean=saved_job(tmp_path,'clean')
    fault=saved_job(tmp_path,'fault',move=True)
    before={p:p.read_bytes() for job in (clean,fault) for p in job.iterdir()}
    labels={name:dict(label=name,korean_sha256=digest(tmp_path/(name+'-output')/'Korean.pdf'))
        for name in ('clean','fault')}
    result=audit_corpus(tmp_path,labels)
    assert result['labeled_clean']==result['labeled_fault']==1
    assert result['false_positive_jobs']==[]
    assert result['missed_fault_jobs']==[]
    assert not result['promotion_evidence_ready']
    assert all(p.read_bytes()==content for p,content in before.items())
    assert not any((job/'region-coverage.json').exists() for job in (clean,fault))


def test_real_review_label_is_not_reused_after_pdf_changes(tmp_path):
    saved_job(tmp_path,'clean')
    labels={'clean':dict(label='clean',korean_sha256='0'*64)}
    result=audit_corpus(tmp_path,labels)
    assert result['labeled_clean']==0 and result['jobs']==0
    assert result['skipped'][0]['reason']=='ValueError'


def test_partial_pipeline_cannot_supply_clean_promotion_evidence(tmp_path):
    job=saved_job(tmp_path,'fault',move=True)
    label=dict(label='clean',korean_sha256=digest(tmp_path/'fault-output'/'Korean.pdf'))
    result=audit_corpus(tmp_path,{job.name:label})
    assert result['labeled_clean']==0
    assert result['ineligible_clean_jobs']==[job.name]
