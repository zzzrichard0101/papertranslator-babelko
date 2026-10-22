from types import SimpleNamespace
import pymupdf as fitz
from babelko.ocr import needs_ocr


def page(text,boxes):
    return SimpleNamespace(rect=fitz.Rect(0,0,600,800),get_text=lambda:text,get_image_info=lambda:[dict(bbox=b) for b in boxes])


def test_fragmented_existing_ocr_is_recognized_but_normal_native_text_is_preserved():
    full=[(0,0,600,800)]
    assert needs_ocr(page('This is a page. '+'t h e E a r t h a n d t h i s '*12,full),'auto')
    assert not needs_ocr(page('This is a normal searchable paragraph with useful words. '*12,full),'auto')
    assert not needs_ocr(page('t h e E a r t h '*12,full),'off')


def test_duplicate_small_images_do_not_count_as_a_full_page_scan():
    assert not needs_ocr(page('',[(0,0,100,100)]*60),'auto')
    assert needs_ocr(page('',[(0,0,600,800)]),'auto')
