from types import SimpleNamespace

from babelko.upstream import prepare
prepare()
from babeldoc.format.pdf.document_il import Box, Mediabox, Page, PdfCharacter, PdfFormula, PdfParagraph, PdfParagraphComposition
from babelko.toc_layout import split_rows


def paragraph(text, x, y):
    chars=[]
    for value in text:
        width=330 if value=='\t' else 5
        chars.append(PdfCharacter(box=Box(x=x,y=y,x2=x+width,y2=y+9),char_unicode=' ' if value=='\t' else value))
        x+=width
    box=Box(x=chars[0].box.x,y=y,x2=chars[-1].box.x2,y2=y+9)
    return PdfParagraph(box=box,unicode=text.replace('\t',' '),layout_label='plain text',
        pdf_paragraph_composition=[PdfParagraphComposition(pdf_character=c) for c in chars])


def test_contents_rows_keep_entry_and_page_number_separate():
    paragraphs=[paragraph('Contents Page',100,700)]
    rows=[('Introduction',8),('Methods',12),('Results',23),('Discussion',38),('References',57)]
    for index,(title,number) in enumerate(rows):
        p=paragraph(title+'\t'+str(number),100,650-index*20)
        paragraphs.append(p)
    # Native analysis can put several rows in one paragraph.
    combined=paragraphs[1]
    for p in paragraphs[2:]:combined.pdf_paragraph_composition.extend(p.pdf_paragraph_composition)
    combined.unicode=' '.join(p.unicode for p in paragraphs[1:])
    page=Page(page_number=3,mediabox=Mediabox(box=Box(x=0,y=0,x2=595,y2=842)),
        pdf_paragraph=[paragraphs[0],combined])
    repairs=split_rows(SimpleNamespace(page=[page]))
    assert len(repairs)==1
    assert [p.unicode for p in page.pdf_paragraph[1:]]==[
        value for title,number in rows for value in (title,str(number))]
    assert all(page.pdf_paragraph[i].layout_label=='fallback_line' for i in range(2,12,2))
    assert all(page.pdf_paragraph[i].box.x>300 for i in range(2,12,2))


def toc_entry(title,number,y,left=100,right=500):
    chars=[];x=left
    for value in title:
        chars.append(PdfCharacter(box=Box(x=x,y=y,x2=x+5,y2=y+9),char_unicode=value));x+=5
    chars.append(PdfCharacter(box=Box(x=x,y=y,x2=right,y2=y+9),char_unicode=' '))
    x=right
    for value in str(number):
        chars.append(PdfCharacter(box=Box(x=x,y=y,x2=x+5,y2=y+9),char_unicode=value));x+=5
    return PdfParagraph(box=Box(x=left,y=y,x2=x,y2=y+9),unicode=f'{title} {number}',
        layout_label='plain text',pdf_paragraph_composition=[PdfParagraphComposition(pdf_character=c) for c in chars])


def page(paragraphs,number=0):
    return Page(page_number=number,mediabox=Mediabox(box=Box(x=0,y=0,x2=595,y2=842)),
        pdf_paragraph=paragraphs)


def test_non_english_heading_and_single_line_entries_are_split():
    entries=[toc_entry(name,n,650-i*25) for i,(name,n) in enumerate([
        ('Présentation',3),('Méthodes',7),('Résultats',12),('Discussion',20)])]
    p=page([paragraph('Sommaire',100,720),*entries]);report={}
    changes=split_rows(SimpleNamespace(page=[p]),report)
    assert report['selected_pages']==[1] and report['restored_paragraphs']==0
    assert len(changes)==4
    assert [item.unicode for item in p.pdf_paragraph[1:]]==[
        'Présentation','3','Méthodes','7','Résultats','12','Discussion','20']


def test_titleless_indented_contents_detected_but_flat_numeric_table_untouched():
    titles=['Introduction','Historical context','Related work','Methods',
        'Data collection','Results','Discussion','References']
    contents=page([toc_entry(title,i*4+1,680-i*25,left=100+(i%2)*22)
        for i,title in enumerate(titles)])
    table=page([toc_entry(f'Method {i}',i+1,680-i*25) for i in range(8)],1)
    report={};changes=split_rows(SimpleNamespace(page=[contents,table]),report)
    assert report['selected_pages']==[1]
    assert len(changes)==8 and len(contents.pdf_paragraph)==16
    assert len(table.pdf_paragraph)==8


def test_headingless_continuation_page_uses_neighbor_evidence():
    first=page([paragraph('목차',100,720)]+[toc_entry(f'장 {i}의 설명',i+1,680-i*25)
        for i in range(4)])
    next_page=page([toc_entry(f'부록 내용 {i}',i+5,680-i*25) for i in range(3)],1)
    report={};split_rows(SimpleNamespace(page=[first,next_page]),report)
    assert report['selected_pages']==[1,2]
    assert report['pages'][1]['reason']=='continuation'
    assert len(next_page.pdf_paragraph)==6


def test_character_loss_during_split_is_repaired(monkeypatch):
    import babelko.toc_layout as layout
    original=layout.new_piece
    def damaged(*args,**kwargs):
        item=original(*args,**kwargs)
        if args[2]=='entry':item.pdf_paragraph_composition[0].pdf_line.pdf_character.pop(0)
        return item
    monkeypatch.setattr(layout,'new_piece',damaged)
    items=[toc_entry(f'Chapter {i}',i+1,680-i*25) for i in range(4)]
    p=page([paragraph('Contents',100,720),*items]);report={}
    split_rows(SimpleNamespace(page=[p]),report)
    assert report['restored_paragraphs']==0
    assert report['pages'][0]['recovered_characters']==4
    assert [item.unicode for item in p.pdf_paragraph[1:3]]==['Chapter 0','1']


def test_irreparable_duplicate_glyph_restores_original_paragraph(monkeypatch):
    import babelko.toc_layout as layout
    original=layout.new_piece
    def damaged(*args,**kwargs):
        item=original(*args,**kwargs)
        if args[2]=='entry':
            chars=item.pdf_paragraph_composition[0].pdf_line.pdf_character
            chars.append(chars[0])
        return item
    monkeypatch.setattr(layout,'new_piece',damaged)
    items=[toc_entry(f'Chapter {i}',i+1,680-i*25) for i in range(4)]
    p=page([paragraph('Contents',100,720),*items]);report={}
    split_rows(SimpleNamespace(page=[p]),report)
    assert report['restored_paragraphs']==4
    assert p.pdf_paragraph[1:]==items


def test_ocr_one_glyph_formula_wrappers_are_split_but_equations_are_preserved():
    entries=[toc_entry(f'Chapter {i}',i+1,680-i*25) for i in range(4)]
    entries[2]=toc_entry('Energy E=mc2',3,630)
    for index in (0,1):
        wrapped=[]
        for composition in entries[index].pdf_paragraph_composition:
            char=composition.pdf_character
            wrapped.append(PdfParagraphComposition(pdf_formula=PdfFormula(
                box=char.box,pdf_character=[char],pdf_curve=[],pdf_form=[])))
        entries[index].pdf_paragraph_composition=wrapped
    original=entries[2]
    position=next(i for i,c in enumerate(original.pdf_paragraph_composition)
        if c.pdf_character and c.pdf_character.char_unicode=='=')
    chars=[c.pdf_character for c in original.pdf_paragraph_composition[position-1:position+2]]
    original.pdf_paragraph_composition[position-1:position+2]=[PdfParagraphComposition(pdf_formula=PdfFormula(
        box=original.box,pdf_character=chars,pdf_curve=[],pdf_form=[]))]
    p=page([paragraph('Contents',100,720),*entries]);report={}
    split_rows(SimpleNamespace(page=[p]),report)
    assert report['pages'][0]['split_entries']==3
    assert report['status']=='incomplete'
    assert report['unresolved_pages']==[{'page':1,'detected':4,'split':3}]
    assert entries[2] in p.pdf_paragraph
    assert [item.unicode for item in p.pdf_paragraph[1:5]]==['Chapter 0','1','Chapter 1','2']


def test_wide_trailing_space_does_not_make_entry_overlap_page_number():
    entries=[toc_entry(f'Chapter {i}',i+1,680-i*25) for i in range(4)]
    spacer=entries[0].pdf_paragraph_composition[-2].pdf_character
    spacer.box.x2=497
    p=page([paragraph('Contents',100,720),*entries]);report={}
    split_rows(SimpleNamespace(page=[p]),report)
    assert report['pages'][0]['split_entries']==4
    assert report['restored_paragraphs']==0
