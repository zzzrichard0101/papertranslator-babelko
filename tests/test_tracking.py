from babelko.validation import tracking_status
from babelko.storage import save


import pytest


@pytest.mark.parametrize('persistent_issue',[False,True])
def test_failed_final_pdf_qa_resumes_from_saved_export(tmp_path,monkeypatch,persistent_issue):
    import pymupdf as fitz
    from babelko.pipeline import revalidate_saved_output
    from babelko.hybrid import OUTPUT_POLICY_REVISION
    from babelko.figure_legends import REVISION as FIGURE_REVISION
    from babelko.storage import digest,read
    folder=tmp_path/'job';out=tmp_path/'result';(folder/'intermediate').mkdir(parents=True);out.mkdir()
    with fitz.open() as doc:
        doc.new_page().insert_text((50,50),'Axis')
        doc.save(folder/'Original.pdf')
    for name in ('Original.pdf','Korean.pdf','Bilingual.pdf'):
        (out/name).write_bytes((folder/'Original.pdf').read_bytes())
    save(folder/'intermediate'/'translate_tracking.json',dict(page=[dict(paragraph=[dict(
        pdf_unicode='Axis',input='Axis',output='Axis')])]))
    sha=digest(folder/'Original.pdf')
    (out/'FigureLegends.html').write_text('No labels',encoding='utf-8')
    save(out/'FigureLegends.json',dict(revision=FIGURE_REVISION,status='passed'))
    save(out/'Quality.json',dict(source_sha256=sha,checks=dict(status='failed',issues=[dict(code='new_replacement_glyph')]),
        translation_tracking=dict(status='passed'),meaning_assurance=dict(status='passed'),
        figures=dict(revision=FIGURE_REVISION,status='passed'),
        hybrid_output_policy=OUTPUT_POLICY_REVISION,unresolved_translation_failures=[]))
    state=dict(status='failed',mode='hybrid',output=str(out),source_sha256=sha,selected=[0],snapshot={},
        output_hashes={name:digest(out/name) for name in ('Original.pdf','Korean.pdf','Bilingual.pdf','Quality.json','FigureLegends.html','FigureLegends.json')})
    if persistent_issue:
        monkeypatch.setattr('babelko.validation.inspect_output',lambda *args:dict(status='failed',
            issues=[dict(code='persistent_layout_issue')],pages=[]))
    stages=[]
    assert revalidate_saved_output(folder,state,lambda message,percent:stages.append((message,percent)))
    assert state['status']==('partial' if persistent_issue else 'completed') and stages[-1][1]==100
    if persistent_issue:assert '검증 문제 1건' in state['error']
    assert read(out/'Quality.json')['checks']['status']==('failed' if persistent_issue else 'passed')
    assert len(read(out/'Quality.json')['checks']['issues'])==int(persistent_issue)
    assert digest(out/'Quality.json')==state['output_hashes']['Quality.json']
    if persistent_issue:
        quality=read(out/'Quality.json');quality['hybrid_output_policy']='old-layout-policy'
        save(out/'Quality.json',quality);state['output_hashes']['Quality.json']=digest(out/'Quality.json')
        assert not revalidate_saved_output(folder,state,lambda *_:pytest.fail('obsolete output revalidated'))


def test_lost_tracked_translation_is_reported_even_if_pdf_exists(tmp_path):
    p=tmp_path/'tracker.json';save(p,dict(page=[dict(paragraph=[dict(pdf_unicode='English source',input='English source',output=None)])]))
    assert tracking_status(p)['status']=='failed' and tracking_status(p)['units_with_no_output']==1


def test_preserved_formula_without_translation_input_is_not_missing(tmp_path):
    p=tmp_path/'tracker.json';save(p,dict(page=[dict(paragraph=[dict(pdf_unicode='Equation',input=None,output=None),dict(pdf_unicode='Source',input='Source',output='번역')])]))
    assert tracking_status(p)['status']=='passed' and tracking_status(p)['parsed_translation_units']==1


def test_empty_tracker_and_whitespace_output_never_pass(tmp_path):
    p=tmp_path/'tracker.json';save(p,dict(page=[]))
    assert tracking_status(p)['status']=='failed'
    save(p,dict(page=[dict(pdf_unicode='English source',input='English source',output='  ')]))
    assert tracking_status(p)['status']=='failed'


def test_old_semantic_certificate_cannot_reuse_completed_job(tmp_path,monkeypatch):
    import pytest
    import babelko.pipeline as pipeline
    from babelko.assurance import REVISION
    from babelko.storage import digest
    from babelko.policy import PROTOCOL,OCR_REVISION
    folder=tmp_path/'jobs'/'job';folder.mkdir(parents=True)
    out=tmp_path/'result';out.mkdir();(folder/'Original.pdf').write_bytes(b'synthetic source')
    def state(revision):
        from babelko.references import REVISION as REFERENCES_REVISION
        from babelko.semantic_guards import REVISION as GUARDS_REVISION
        from babelko.figure_legends import REVISION as FIGURE_REVISION
        save(out/'Quality.json',dict(meaning_assurance=dict(revision=revision),references=dict(revision=REFERENCES_REVISION),
            translation_guards=dict(revision=GUARDS_REVISION),figures=dict(revision=FIGURE_REVISION,status='passed')))
        value=dict(protocol=PROTOCOL,ocr_revision=OCR_REVISION,mode='hybrid',status='completed',
            output=str(out),output_hashes={'Quality.json':digest(out/'Quality.json')},source_sha256=digest(folder/'Original.pdf'))
        save(folder/'state.json',value);return value
    monkeypatch.setattr(pipeline,'root',lambda:tmp_path)
    monkeypatch.setattr(pipeline,'prepare',lambda:None)
    def stop(*_):raise RuntimeError('entered updated processing')
    monkeypatch.setattr(pipeline,'assets',stop)
    expected=state(REVISION);assert pipeline.run(folder)==expected
    state('old-auditor')
    with pytest.raises(RuntimeError,match='entered updated processing'):pipeline.run(folder)
    value=state(REVISION)
    save(out/'Quality.json',dict(meaning_assurance=dict(revision=REVISION)))
    value['output_hashes']['Quality.json']=digest(out/'Quality.json');save(folder/'state.json',value)
    with pytest.raises(RuntimeError,match='entered updated processing'):pipeline.run(folder)


def test_experimental_completed_job_requires_current_spatial_and_context_evidence(tmp_path,monkeypatch):
    import pytest
    import babelko.pipeline as pipeline
    from babelko.assurance import REVISION
    from babelko.references import REVISION as REFERENCES
    from babelko.region_ledger import REVISION as REGIONS
    from babelko.document_context import REVISION as CONTEXT
    from babelko.semantic_guards import REVISION as GUARDS
    from babelko.figure_legends import REVISION as FIGURES
    from babelko.policy import PROTOCOL,OCR_REVISION
    from babelko.storage import digest
    folder=tmp_path/'jobs'/'job';folder.mkdir(parents=True)
    out=tmp_path/'result';out.mkdir();(folder/'Original.pdf').write_bytes(b'synthetic source')
    monkeypatch.setattr(pipeline,'root',lambda:tmp_path);monkeypatch.setattr(pipeline,'prepare',lambda:None)
    def stop(*_):raise RuntimeError('updated spatial processing')
    monkeypatch.setattr(pipeline,'assets',stop)
    for region_revision,context_revision,region_status in [(REGIONS,CONTEXT,'passed'),('old',CONTEXT,'passed'),(REGIONS,'old','passed'),(REGIONS,CONTEXT,'failed')]:
        save(out/'Quality.json',dict(meaning_assurance=dict(revision=REVISION),references=dict(revision=REFERENCES),
            translation_guards=dict(revision=GUARDS),figures=dict(revision=FIGURES,status='passed'),
            region_coverage=dict(revision=region_revision,status=region_status),document_context=dict(revision=context_revision)))
        state=dict(protocol=PROTOCOL,ocr_revision=OCR_REVISION,mode='hybrid',status='completed',snapshot=dict(experimental_pipeline=True),
            output=str(out),output_hashes={'Quality.json':digest(out/'Quality.json')},source_sha256=digest(folder/'Original.pdf'))
        save(folder/'state.json',state)
        if region_revision==REGIONS and context_revision==CONTEXT and region_status=='passed':assert pipeline.run(folder)==state
        else:
            with pytest.raises(RuntimeError,match='updated spatial processing'):pipeline.run(folder)
