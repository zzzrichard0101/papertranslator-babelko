from pathlib import Path
import pymupdf as fitz
from babelko.ocr import prepare
from babelko.pipeline import compose
from babelko.pdf_preservation import optimize,restore_original_index


def document(path):
    with fitz.open() as doc:
        page=doc.new_page(width=300,height=400)
        page.insert_textbox(fitz.Rect(20,20,280,350),'Native PDF text. '*30)
        page.draw_rect(fitz.Rect(20,320,200,380),fill=(.2,.6,.1,0),color=None)
        doc.xref_set_key(page.xref,'Group','<< /S /Transparency /CS /DeviceCMYK /I false /K false >>')
        doc.set_toc([[1,'Chapter',1]])
        doc.save(path)


def test_no_ocr_is_byte_exact_and_preserves_navigation_and_color(tmp_path):
    src=tmp_path/'s.pdf';out=tmp_path/'i.pdf';document(src)
    assert prepare(src,out,mode='auto')==[]
    assert src.read_bytes()==out.read_bytes()


def test_composition_preserves_cmyk_source_pixels_and_outlines(tmp_path):
    src=tmp_path/'s.pdf';ko=tmp_path/'ko.pdf';dual=tmp_path/'dual.pdf';document(src);optimize(src,ko)
    compose(src,ko,dual,[0])
    with fitz.open(src) as a,fitz.open(dual) as b:
        assert b.get_toc()==a.get_toc()
        original=a[0].get_pixmap(alpha=False)
        left=b[0].get_pixmap(clip=fitz.Rect(0,0,300,400),alpha=False)
        assert original.samples==left.samples


def test_composition_preserves_rotated_source_view_and_original_file(tmp_path):
    src=tmp_path/'rotated.pdf';dual=tmp_path/'dual.pdf'
    with fitz.open() as doc:
        p=doc.new_page(width=300,height=500);p.insert_text((30,60),'A rotated source view.');p.set_rotation(90);doc.save(src)
    original_bytes=src.read_bytes();compose(src,src,dual,[0]);assert src.read_bytes()==original_bytes
    with fitz.open(src) as a,fitz.open(dual) as b:
        source=a[0].get_pixmap(alpha=False);left=b[0].get_pixmap(clip=a[0].rect,alpha=False)
        assert source.samples==left.samples
    prepared=tmp_path/'normalized.pdf'
    assert prepare(src,prepared,mode='off')==[]
    with fitz.open(src) as a,fitz.open(prepared) as b:
        assert b[0].rotation==0
        from babelko.storage import read
        report=read(prepared.with_suffix('.transformations.json'))
        assert report['pages'][0]['restore_rotation']==90
        b[0].set_rotation(report['pages'][0]['restore_rotation'])
        assert b[0].get_pixmap(alpha=False).samples==a[0].get_pixmap(alpha=False).samples


def test_untranslated_index_uses_exact_original_page_pixels(tmp_path):
    original=tmp_path/'original.pdf';korean=tmp_path/'korean.pdf'
    for path,prefix in [(original,'Original'),(korean,'Korean')]:
        with fitz.open() as doc:
            for n in range(3):
                page=doc.new_page();page.insert_text((30,70),f'{prefix} page {n+1}')
            doc.save(path)
    before=original.read_bytes()
    report=dict(paragraphs=[dict(source_page=3,reason='index_section')])
    assert restore_original_index(original,korean,[0,1,2],report)==[3]
    assert original.read_bytes()==before
    with fitz.open(original) as source,fitz.open(korean) as translated:
        assert len(translated)==3
        assert 'Korean page 2' in translated[1].get_text()
        assert 'Original page 3' in translated[2].get_text()
        assert translated[2].get_pixmap().samples==source[2].get_pixmap().samples
