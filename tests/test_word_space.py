import pymupdf

from babelko.word_space import build


def test_word_space_tracks_local_occurrences_and_relations(tmp_path):
    source = tmp_path / "paper.pdf"
    with pymupdf.open() as document:
        document.new_page().insert_text((40, 60), "Quasar nebula quasar telescope. Quasar nebula.")
        document.new_page().insert_text((40, 60), "Telescope nebula spectrum.")
        document.save(source)
    result = build(source)
    by_word = {point["word"]: point for point in result["points"]}
    assert result["status"] == "ready"
    assert by_word["quasar"]["count"] == 3
    assert by_word["nebula"]["page_hits"] == 2
    assert by_word["spectrum"]["first_page"] == 2
    assert "nebula" in by_word["quasar"]["neighbors"]
    assert any(edge["a"] != edge["b"] for edge in result["edges"])


def test_word_space_reuses_existing_local_ocr_for_image_only_page(tmp_path):
    source = tmp_path / "scan.pdf"
    ocr_dir = tmp_path / "ocr"
    ocr_dir.mkdir()
    with pymupdf.open() as document:
        document.new_page()
        document.save(source)
    with pymupdf.open() as document:
        document.new_page().insert_text((40, 60), "Aurora borealis aurora particles.")
        document.save(ocr_dir / "page-1.pdf")
    result = build(source, ocr_dir=ocr_dir)
    assert result["ocr_pages"] == 1
    assert result["blank_pages"] == 0
    assert "aurora" in {point["word"] for point in result["points"]}


def test_word_space_has_a_bounded_display_and_no_pdf_page_images(tmp_path):
    source = tmp_path / "many.pdf"
    with pymupdf.open() as document:
        document.new_page().insert_text((40, 60), "alpha beta gamma delta epsilon zeta eta theta")
        document.save(source)
    result = build(source, max_terms=4)
    assert len(result["points"]) == 4
    assert all(set(point).isdisjoint({"preview", "image", "page_bitmap"}) for point in result["points"])
