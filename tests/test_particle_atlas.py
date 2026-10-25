import pymupdf

from babelko.particle_atlas import MAX_PARTICLES, snapshot


def test_atlas_uses_pdf_coordinates_and_qualified_status(tmp_path):
    source = tmp_path / 'source.pdf'
    with pymupdf.open() as document:
        page = document.new_page(width=400, height=600)
        page.insert_text((40, 70), 'A paragraph about source alignment and translation quality.')
        page.draw_rect(pymupdf.Rect(40, 100, 150, 180), color=(.1, .2, .3))
        document.save(source)
    coverage = {'pages': [dict(source_page=1, suspected_missing=[dict(box=[35, 50, 380, 75])])]}
    atlas = snapshot(source, 0, coverage=coverage, translated_pages={1}, selected_pages={1})
    assert atlas['source_page'] == atlas['total_pages'] == 1
    assert atlas['suspect_regions'] == 1
    assert atlas['regions'][0]['status'] == 'source_gap_suspected'
    assert 0 < atlas['regions'][0]['x'] < 1
    assert 0 < atlas['regions'][0]['y'] < 1
    assert sum(row['particles'] for row in atlas['regions']) <= MAX_PARTICLES


def test_atlas_does_not_claim_translation_for_an_unprocessed_page(tmp_path):
    source = tmp_path / 'source.pdf'
    with pymupdf.open() as document:
        document.new_page().insert_text((50, 50), 'A source sentence is visible here.')
        document.save(source)
    atlas = snapshot(source, 0)
    assert atlas['regions'][0]['status'] == 'unprocessed'
    assert atlas['regions'][0]['kind'] == 'text'


def test_atlas_marks_only_the_selected_output_page_as_created(tmp_path):
    source = tmp_path / 'source.pdf'
    with pymupdf.open() as document:
        document.new_page().insert_text((50, 50), 'First page.')
        document.new_page().insert_text((50, 50), 'Second page.')
        document.save(source)
    first = snapshot(source, 0, selected_pages={1}, translated_pages={1})
    second = snapshot(source, 1, selected_pages={1}, translated_pages={1})
    assert first['regions'][0]['status'] == 'output_created'
    assert second['regions'][0]['status'] == 'outside_selection'
