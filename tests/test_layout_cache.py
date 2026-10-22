import gzip,json
import pytest
import pymupdf as fitz
from babelko.upstream import prepare
from babelko.storage import read,save


def fixture():
    prepare()
    from babeldoc.format.pdf.document_il import il_version_1 as il
    from babeldoc.format.pdf.document_il.frontend.il_creater_active_support import LazyPassthroughInstruction
    return il.Document(total_pages=1,page=[il.Page(page_number=0,pdf_paragraph=[il.PdfParagraph(unicode='Original source',debug_id='fixed',box=il.Box(1,2,30,40),pdf_style=il.PdfStyle(font_id='F1',font_size=10))],base_operations=il.BaseOperations(value='q Q'))])


def test_native_dataclass_roundtrip_preserves_full_source_structure(tmp_path):
    from babelko.layout_cache import LayoutCache
    from babeldoc.format.pdf.document_il.xml_converter import XMLConverter
    docs=fixture();cache=LayoutCache(tmp_path);cache.store('signature',docs);restored=cache.load('signature')
    assert restored is not None and XMLConverter().to_json(restored)==XMLConverter().to_json(docs)
    assert cache.load('different-input-or-config') is None
    restored.page[0].pdf_paragraph[0].unicode='Translated'
    assert cache.load('signature').page[0].pdf_paragraph[0].unicode=='Original source'


def test_corrupt_cache_falls_back_without_deserializing_untrusted_classes(tmp_path):
    from babelko.layout_cache import LayoutCache
    cache=LayoutCache(tmp_path);cache.store('signature',fixture());manifest=read(cache.manifest)
    path=cache.base/manifest['generation']/'page-0.json.gz';path.write_bytes(b'corrupt')
    assert cache.load('signature') is None
    manifest['generation']='../escape';save(cache.manifest,manifest);assert cache.load('signature') is None


def test_schema_rejects_changed_fields_and_wrong_types():
    from babelko.layout_cache import decode
    from babeldoc.format.pdf.document_il import il_version_1 as il
    with pytest.raises(ValueError):decode(il.Box,dict(x=1,y=2,x2=3,y2='wrong'))
    with pytest.raises(ValueError):decode(il.Box,dict(x=1,y=2,x2=3,y2=4,extra='ignored'))
    assert decode(bool,1)==1 and type(decode(bool,1)) is int
    assert decode(bool,'a','debug_info')=='a'
    with pytest.raises(ValueError):decode(bool,'a','bold')


def test_prepared_pdf_hash_ignores_only_save_id_and_detects_content_changes(tmp_path):
    from babelko.layout_cache import prepared_hash
    with fitz.open() as doc:
        doc.new_page().insert_text((30,40),'Original');doc.save(tmp_path/'a.pdf')
    with fitz.open(tmp_path/'a.pdf') as a:
        before=prepared_hash(a);a.save(tmp_path/'b.pdf')
    with fitz.open(tmp_path/'b.pdf') as b:
        assert prepared_hash(b)==before
        b[0].insert_text((30,80),'Changed');assert prepared_hash(b)!=before


def test_cache_keeps_shared_styles_and_characters_across_compositions_and_pages(tmp_path):
    from babelko.layout_cache import LayoutCache
    from babeldoc.format.pdf.document_il import il_version_1 as il
    style=il.PdfStyle(font_id='F1',font_size=10)
    char=il.PdfCharacter(char_unicode='A',pdf_style=style)
    p=il.Page(page_number=0,pdf_character=[char],pdf_paragraph=[il.PdfParagraph(pdf_style=style,pdf_paragraph_composition=[il.PdfParagraphComposition(pdf_character=char)])])
    q=il.Page(page_number=1,pdf_character=[il.PdfCharacter(char_unicode='B',pdf_style=style)])
    cache=LayoutCache(tmp_path);cache.store('aliases',il.Document(page=[p,q],total_pages=2));docs=cache.load('aliases')
    a,b=docs.page
    assert a.pdf_character[0] is a.pdf_paragraph[0].pdf_paragraph_composition[0].pdf_character
    assert a.pdf_character[0].pdf_style is a.pdf_paragraph[0].pdf_style is b.pdf_character[0].pdf_style
