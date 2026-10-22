import copy
from types import SimpleNamespace as NS
import pytest
from babelko.scan_evidence import corrections,apply,rule_only,raster_single_glyph
from babelko.translator import number_errors


@pytest.mark.parametrize('source,target',[
    ('World War II ended in 1945.','제2차 세계대전은 1945년에 끝났다.'),
    ('Throughout Part II and Part III.','제2부와 제3부 전반에서.'),
    ('Thirty-four participants attended.','34명이 참석했다.'),
    ('Mid-20th century theory.','20세기 중반의 이론.'),
])
def test_equivalent_number_spellings(source,target):assert not number_errors(source,target)


@pytest.mark.parametrize('source,target',[
    ('World War II ended in 1945.','제3차 세계대전은 1945년에 끝났다.'),
    ('Thirty-four participants attended.','30명이 참석했다.'),
    ('The temperature is -20.','기온은 20이다.'),
    ('The variable I is 10.','변수 1은 10이다.'),
])
def test_number_guard_remains_strict(source,target):assert number_errors(source,target)


def test_ocr_correction_requires_two_sided_independent_image_evidence():
    source='Go 10 its Website to find information.'
    result,edits=corrections(source,[dict(text='Go to its Website to find information.',score=.99)])
    # Not enough left context: never guess, even on an apparently obvious typo.
    assert result==source and not edits
    source='The authors recommend that you go 10 its Website to find information.'
    good=[dict(text='The authors recommend that you go to its Website to find information.',score=.99)]
    result,edits=corrections(source,good)
    assert result==source.replace('10','to') and len(edits)==1
    assert corrections(source,[{**good[0],'score':.8}])==(source,[])
    assert corrections(source,[dict(text=source,score=.99)])==(source,[])
    assert number_errors(source,'저자들은 웹사이트에 방문하라고 권한다.')


def test_scan_typography_changes_only_output_styles_without_shared_mutation():
    shared=NS(font_size=40,font_id='f1');formula=NS(pdf_style=shared)
    run=NS(pdf_style=shared,unicode='번역문')
    p=NS(debug_id='p',pdf_style=shared,pdf_paragraph_composition=[NS(pdf_same_style_unicode_characters=run,pdf_formula=None),NS(pdf_same_style_unicode_characters=None,pdf_formula=formula)])
    docs=NS(page=[NS(page_number=0,pdf_paragraph=[p])]);apply(docs,{(0,'p'):dict(size=11)})
    assert run.pdf_style.font_size==p.pdf_style.font_size==11
    assert formula.pdf_style.font_size==shared.font_size==40 and run.unicode=='번역문'


def test_rule_exclusion_needs_pixel_evidence_and_retains_real_text():
    import pymupdf as f
    with f.open() as d:
        p=d.new_page(width=400,height=200);p.draw_line((30,80),(350,80),width=1)
        assert rule_only(p,NS(x=25,x2=355,y=110,y2=130))
        p.insert_text((30,120),'The result is 10, not 20.',fontsize=12)
        assert not rule_only(p,NS(x=25,x2=355,y=70,y2=90))


def test_raster_single_glyph_preserves_a_scanned_section_letter_but_not_a_heading():
    import pymupdf as f
    def scanned(label):
        with f.open() as vector:
            page=vector.new_page(width=600,height=180)
            page.draw_line((70,50),(530,50),width=1)
            page.insert_text((290,79),label,fontname='hebo',fontsize=26)
            page.draw_line((70,90),(530,90),width=1)
            pixels=page.get_pixmap(matrix=f.Matrix(2,2)).tobytes('png')
        pdf=f.open();page=pdf.new_page(width=600,height=180)
        page.insert_image(page.rect,stream=pixels)
        return pdf
    box=NS(x=70,x2=530,y=180-95,y2=180-45)
    with scanned('C') as pdf:
        assert raster_single_glyph(pdf[0],box,'C BE Nr re TI SI TTC Tm a i.')
    with scanned('Research') as pdf:
        assert not raster_single_glyph(pdf[0],box,'Research methods and context')


def test_band_reconstruction_keeps_neighboring_runs_and_original_scan():
    import pymupdf as f
    from babelko.scan_evidence import reconstruct_band
    with f.open() as original,f.open() as derived:
        src=original.new_page(width=400,height=200)
        src.insert_text((30,80),'Correct source row',fontsize=12)
        p=derived.new_page(width=400,height=200)
        p.insert_text((30,20),'Outside top',fontsize=12)
        p.insert_text((30,80),'a',fontsize=48)
        # Its bbox overlaps the band. Redaction would delete its first letters.
        p.insert_text((30,108),'Neighbor must survive',fontsize=12)
        before=[original.xref_stream(x) for x in src.get_contents()]
        count=reconstruct_band(p,src,f.Rect(0,45,400,100),[dict(text='Correct source row',score=.99,bbox=[30,65,150,84])])
        assert count==1 and [original.xref_stream(x) for x in src.get_contents()]==before
        text=p.get_text()
        assert 'Correct source row' in text and '\na\n' not in text
        assert 'Outside top' in text and 'Neighbor must survive' in text
        assert max(s['size'] for b in p.get_text('dict')['blocks'] for l in b.get('lines',[]) for s in l['spans'])<20


def test_incomplete_second_ocr_cannot_delete_a_table_row_or_duplicate_it():
    import pymupdf as f
    from babelko.scan_evidence import reconstruct_band
    with f.open() as original,f.open() as derived:
        src=original.new_page(width=400,height=200);p=derived.new_page(width=400,height=200)
        p.insert_text((20,80),'Treatment A',fontsize=12)
        p.insert_text((170,80),'Important unmatched outcome',fontsize=12)
        n=reconstruct_band(p,src,f.Rect(0,45,400,100),[dict(text='Treatment A',score=.99,bbox=[20,65,100,84])])
        text=p.get_text()
        assert 'Important unmatched outcome' in text
        assert text.count('Treatment A')==1


def test_agreed_word_keeps_its_text_while_inflated_ocr_font_is_repaired():
    import pymupdf as f
    from babelko.scan_evidence import reconstruct_band
    with f.open() as original,f.open() as derived:
        src=original.new_page(width=400,height=200);p=derived.new_page(width=400,height=200)
        src.insert_text((50,80),'behavioral therapy',fontsize=12)
        p.insert_text((50,80),'behavioral',fontsize=48)
        for y in [20,120,160]:p.insert_text((20,y),'Ordinary neighboring row',fontsize=12)
        reconstruct_band(p,src,f.Rect(0,40,400,105),[dict(text='behavioral therapy',score=.88,bbox=[50,67,250,84])])
        spans=[s for b in p.get_text('dict')['blocks'] for l in b.get('lines',[]) for s in l['spans']]
        word=next(s for s in spans if s['text']=='behavioral')
        assert word['size']<20 and p.get_text().count('behavioral')==1
