from types import SimpleNamespace as Obj
import pymupdf as fitz
from babeldoc.format.pdf.document_il import Box,PdfStyle
from babelko.table_flow import cells,merge_cells
from babelko.hybrid import errors


def test_segmented_table_rules_bound_prose_and_preserve_items_math_and_columns(tmp_path):
    path=tmp_path/'table.pdf'
    with fitz.open() as pdf:
        page=pdf.new_page(width=300,height=200)
        for y in [20,100,180]:
            page.draw_line((0,y),(100,y));page.draw_line((100,y),(300,y))
        pdf.save(path)
    def p(text,x,y):return Obj(unicode=text,box=Box(x,y,x+70,y+10),layout_label='fallback_line',xobj_id=0,
                              pdf_style=PdfStyle(font_id='F1',font_size=10),pdf_paragraph_composition=[object()])
    a=p('CONTROL 1: Staff must',10,160);b=p('remain responsible for all decisions.',10,148)
    c=p('CONTROL 1.1: No causal',110,160);d=p('effect can be inferred from this value.',110,148)
    e=p('CONTROL 1.2: Review the formula.',110,132);f=p('Keep the original equation unchanged.',110,120)
    numeric=p('12',10,60);before=[t for v in [a,b,c,d,e,f,numeric] for t in v.pdf_paragraph_composition]
    with fitz.open(path) as pdf:regions=cells(pdf[0])
    assert len(regions)==4
    result,changes=merge_cells([a,b,c,d,e,f,numeric],regions)
    assert len(result)==4 and len(changes)==3 and numeric in result
    assert a.unicode=='CONTROL 1: Staff must remain responsible for all decisions.'
    assert c.unicode=='CONTROL 1.1: No causal effect can be inferred from this value.'
    assert e.unicode=='CONTROL 1.2: Review the formula. Keep the original equation unchanged.'
    assert sorted(map(id,before))==sorted(id(t) for p in result for t in p.pdf_paragraph_composition)
    assert a.box.x2<100 and c.box.x>=100 and e.box.y>100


def test_page_rules_without_repeated_column_junctions_do_not_prove_cells():
    with fitz.open() as pdf:
        page=pdf.new_page(width=300,height=200)
        for y in [20,100,180]:page.draw_line((0,y),(300,y))
        assert cells(page)==[]


def test_source_entry_identifier_survives_translation_even_when_numbers_match():
    assert errors('GOVERN 1.5: Review the risk.','관리 1.5: 위험을 검토한다.')
    assert not errors('GOVERN 1.5: Review the risk.','GOVERN 1.5: 위험을 검토한다.')
