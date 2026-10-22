from babelko.validation import tracking_status
from babelko.storage import save


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
        save(out/'Quality.json',dict(meaning_assurance=dict(revision=revision),references=dict(revision=REFERENCES_REVISION)))
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
    from babelko.policy import PROTOCOL,OCR_REVISION
    from babelko.storage import digest
    folder=tmp_path/'jobs'/'job';folder.mkdir(parents=True)
    out=tmp_path/'result';out.mkdir();(folder/'Original.pdf').write_bytes(b'synthetic source')
    monkeypatch.setattr(pipeline,'root',lambda:tmp_path);monkeypatch.setattr(pipeline,'prepare',lambda:None)
    def stop(*_):raise RuntimeError('updated spatial processing')
    monkeypatch.setattr(pipeline,'assets',stop)
    for region_revision,context_revision,region_status in [(REGIONS,CONTEXT,'passed'),('old',CONTEXT,'passed'),(REGIONS,'old','passed'),(REGIONS,CONTEXT,'failed')]:
        save(out/'Quality.json',dict(meaning_assurance=dict(revision=REVISION),references=dict(revision=REFERENCES),
            region_coverage=dict(revision=region_revision,status=region_status),document_context=dict(revision=context_revision)))
        state=dict(protocol=PROTOCOL,ocr_revision=OCR_REVISION,mode='hybrid',status='completed',snapshot=dict(experimental_pipeline=True),
            output=str(out),output_hashes={'Quality.json':digest(out/'Quality.json')},source_sha256=digest(folder/'Original.pdf'))
        save(folder/'state.json',state)
        if region_revision==REGIONS and context_revision==CONTEXT and region_status=='passed':assert pipeline.run(folder)==state
        else:
            with pytest.raises(RuntimeError,match='updated spatial processing'):pipeline.run(folder)
