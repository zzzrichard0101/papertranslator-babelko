from types import SimpleNamespace as Obj
from babelko.text_structure import normalize_input,caption_word_repairs,cross_boundary_word_repairs,repair_caption_input
from babelko.hybrid import errors
from babeldoc.format.pdf.document_il.midend.il_translator import FormulaPlaceholder,RichTextPlaceholder


def char(text,x):return Obj(char_unicode=text,box=Obj(x=x,x2=x+3,y=0,y2=10))


def test_prose_day_grouped_with_bullet_is_exposed_without_mutating_source():
    formula=Obj(pdf_character=[char('•',0),char(' ',3),char('6',6),char(' ',9)],box=Obj(x=0,x2=12,y=0,y2=10))
    p=FormulaPlaceholder(1,formula,'{v1}',r'\{v1\}')
    value=Obj(unicode='{v1}October 1944, she arrived.',placeholders=[p])
    assert normalize_input(value).unicode=='{v1}6 October 1944, she arrived.'
    assert ''.join(c.char_unicode for c in value.placeholders[0].formula.pdf_character)=='•  '
    assert ''.join(c.char_unicode for c in formula.pdf_character)=='• 6 '


def test_math_and_numbered_bullets_remain_opaque_outside_named_dates():
    formula=Obj(pdf_character=[char('•',0),char('6',3)],box=Obj(x=0,x2=6,y=0,y2=10))
    p=FormulaPlaceholder(1,formula,'{v1}',r'\{v1\}')
    value=Obj(unicode='{v1}Training parameters',placeholders=[p])
    assert normalize_input(value).unicode=='{v1}Training parameters'
    assert value.placeholders[0] is p


def test_typographic_ordinal_suffix_becomes_prose_not_permanent_english():
    composition=Obj(pdf_character=[char('t',0),char('h',3)])
    p=RichTextPlaceholder(2,composition,"<style id='2'>",'</style>','left','right')
    value=Obj(unicode="Think of your 7<style id='2'>th</style> grade notebook",placeholders=[p])
    assert normalize_input(value).unicode=='Think of your 7th grade notebook'
    assert value.placeholders==[]
    assert errors('Think of your 7th grade notebook','7th학년 공책을 떠올려보세요.')


def test_split_caption_word_uses_repeated_document_vocabulary_only():
    def paragraph(key,text,y,label='figure_caption'):
        return Obj(debug_id=key,unicode=text,layout_label=label,box=Obj(x=0,x2=300,y=y,y2=y+10),pdf_style=Obj(font_size=10))
    left=paragraph('a','We use Gaussianan',100);right=paragraph('b','isotropy disabled and enabled.',88)
    body=paragraph('c','Gaussian Gaussian anisotropy anisotropy',200,'text')
    doc=Obj(page=[Obj(pdf_paragraph=[body,left,right])])
    repairs=caption_word_repairs(doc)
    assert repair_caption_input(Obj(unicode=left.unicode),repairs['a']).unicode=='We use Gaussian'
    assert repair_caption_input(Obj(unicode=right.unicode),repairs['b']).unicode=='anisotropy disabled and enabled.'
    body.unicode='Gaussian anisotropy'
    assert caption_word_repairs(doc)=={}


def test_cross_column_hyphenated_word_is_whole_in_one_model_input():
    a=Obj(debug_id='left',unicode='The result follows. In sum-',layout_label='plain text')
    b=Obj(debug_id='right',unicode='mary, the bound decreases.',layout_label='plain text')
    doc=Obj(page=[Obj(page_number=0,pdf_paragraph=[a,b])])
    repairs=cross_boundary_word_repairs(doc)
    left=Obj(unicode="<style id='1'>The result follows. In sum-</style>")
    right=Obj(unicode="<style id='1'>mary, the bound decreases.</style>")
    assert repair_caption_input(left,repairs['left']).unicode=="<style id='1'>The result follows. </style>"
    assert repair_caption_input(right,repairs['right']).unicode=="<style id='1'>In summary, the bound decreases.</style>"
    assert a.unicode=='The result follows. In sum-' and b.unicode=='mary, the bound decreases.'


def test_cross_column_glued_word_is_not_left_as_an_unintelligible_suffix():
    a=Obj(debug_id='left',unicode='across domainsviacoordinatetransfor-',layout_label='plain text')
    b=Obj(debug_id='right',unicode='mations orstructural priors.',layout_label='plain text')
    doc=Obj(page=[Obj(page_number=0,pdf_paragraph=[a,b])])
    repairs=cross_boundary_word_repairs(doc)
    assert repair_caption_input(Obj(unicode=a.unicode),repairs['left']).unicode=='across '
    assert repair_caption_input(Obj(unicode=b.unicode),repairs['right']).unicode=='domainsviacoordinatetransformations orstructural priors.'


def test_hyphenated_fallback_lines_merge_without_crossing_columns_or_new_rows():
    from babelko.text_structure import merge_hyphenated_fallbacks
    def p(text,x,y):return Obj(unicode=text,box=Obj(x=x,x2=x+200,y=y,y2=y+10),layout_label='fallback_line',xobj_id=0,pdf_style=Obj(font_size=10),pdf_paragraph_composition=[text])
    a=p('Responsibilities for configura-',0,100);b=p('tions and oversight of systems.',0,88);other=p('tions in another column.',300,88)
    doc=Obj(page=[Obj(page_number=0,pdf_paragraph=[a,b,other])]);changes=merge_hyphenated_fallbacks(doc)
    assert len(changes)==1 and doc.page[0].pdf_paragraph==[a,other]
    assert a.unicode=='Responsibilities for configura- tions and oversight of systems.' and a.box.y==88
    a=p('This is a complete row.',0,100);b=p('another row starts here.',0,88)
    assert merge_hyphenated_fallbacks(Obj(page=[Obj(pdf_paragraph=[a,b])]))==[]
    a=p('Responsibilities are planned and or-',0,100);b=p('ganized daily.',0,88)
    assert len(merge_hyphenated_fallbacks(Obj(page=[Obj(pdf_paragraph=[a,b])])))==1
    assert a.unicode=='Responsibilities are planned and or- ganized daily.'


def test_prose_misclassified_as_formula_is_exposed_but_equations_are_preserved():
    from babelko.text_structure import expose_prose_formulas
    from babeldoc.format.pdf.document_il import Box,PdfCharacter,PdfStyle,PdfFormula,PdfParagraph,PdfParagraphComposition,VisualBbox
    style=PdfStyle(font_id='F1',font_size=10)
    def paragraph(text,x):
        chars=[]
        for i,c in enumerate(text):
            box=Box(x+i*6,100,x+(i+1)*6,110)
            chars.append(PdfCharacter(char_unicode=c,box=box,visual_bbox=VisualBbox(box=box),pdf_style=style,xobj_id=0,vertical=False))
        box=Box(x,100,x+len(text)*6,110)
        return PdfParagraph(box=box,pdf_style=style,xobj_id=0,unicode=text,layout_label='abandon',debug_id='test'+str(x),
            pdf_paragraph_composition=[PdfParagraphComposition(pdf_formula=PdfFormula(box=box,pdf_character=chars))])
    a=paragraph('A Pytho',0);b=paragraph('n Toolbox for the Analysis of Learnin',42);c=paragraph('g',b.box.x2)
    a.pdf_style=None;b.pdf_style=None;c.pdf_style=None
    doc=Obj(page=[Obj(page_number=0,pdf_paragraph=[a,b,c])]);changes=expose_prose_formulas(doc)
    assert len(changes)==1 and changes[0]['after']=='A Python Toolbox for the Analysis of Learning'
    assert len(doc.page[0].pdf_paragraph)==1 and a.pdf_paragraph_composition[0].pdf_line
    assert a.pdf_style.font_id=='F1' and a.pdf_style.font_size==10
    equation=paragraph('sum of the terms x = y and the remainder',0)
    doc=Obj(page=[Obj(pdf_paragraph=[equation])]);assert expose_prose_formulas(doc)==[]
    assert equation.pdf_paragraph_composition[0].pdf_formula
