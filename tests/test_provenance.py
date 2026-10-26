from babelko.provenance import build, export
from babelko.storage import digest, read, save


def test_identical_paragraph_occurrences_link_to_distinct_render_failures(tmp_path):
    source = tmp_path / 'SourceEvidence.json'
    tracker = tmp_path / 'translate_tracking.json'
    text = 'A repeated clinical observation appears twice.'
    save(source, dict(rows=[
        dict(id='first', extractor='il_paragraph', source_page=1, text=text),
        dict(id='second', extractor='il_paragraph', source_page=1, text=text)]))
    save(tracker, dict(page=[dict(paragraph=[
        dict(pdf_unicode=text, input=text, output='첫 번째 번역'),
        dict(pdf_unicode=text, input=text, output='두 번째 번역')])],
        cross_page=[], cross_column=[]))
    rendered = dict(missing=[dict(tracked_unit=1, page=1)])
    result = build(source, tracker, [0], rendered)
    assert result['tracked_units'] == result['matched_units'] == 2
    assert [row['source_region_ids'] for row in result['rows']] == [['first'], ['second']]
    assert rendered['missing'][0]['source_region_ids'] == ['second']
    assert rendered['missing'][0]['source_page'] == 1
    manifest = export(tmp_path, source, tracker, [0], dict(missing=[]))
    assert manifest['status'] == 'available'
    assert digest(tmp_path / 'Provenance.json') == manifest['sha256']
    assert read(tmp_path / 'Provenance.json')['rows'][0]['source_region_ids'] == ['first']


def test_unmatched_tracker_unit_remains_explicit(tmp_path):
    source = tmp_path / 'SourceEvidence.json'
    tracker = tmp_path / 'translate_tracking.json'
    save(source, dict(rows=[dict(id='one', extractor='il_paragraph', source_page=1,
                                 text='The original paragraph.')]))
    save(tracker, dict(page=[dict(paragraph=[dict(pdf_unicode='A different paragraph.',
                                                  input='A different paragraph.', output='다른 번역')])],
                       cross_page=[], cross_column=[]))
    result = build(source, tracker, [0], dict(missing=[]))
    assert result['unlinked_units'] == 1
    assert result['rows'][0]['match'] == 'unlinked'
