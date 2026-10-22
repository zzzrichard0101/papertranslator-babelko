from collections import Counter
from babeldoc.format.pdf.document_il import Box,VisualBbox,PdfCharacter,PdfParagraph,PdfParagraphComposition,PdfStyle
from babeldoc.format.pdf.document_il.midend.paragraph_finder import ParagraphFinder
from babelko.source_flow import merge_raw


def chars(text,x,y=100):
    style=PdfStyle(font_id='F1',font_size=10)
    return [PdfCharacter(char_unicode=c,pdf_character_id=ord(c),box=Box(x+i*5,y,x+(i+1)*5,y+10),visual_bbox=VisualBbox(box=Box(x+i*5,y,x+(i+1)*5,y+10)),pdf_style=style,xobj_id=0,vertical=False) for i,c in enumerate(text)]


def paragraph(glyphs):
    return PdfParagraph(box=Box(min(c.box.x for c in glyphs),100,max(c.box.x2 for c in glyphs),110),layout_label='plain text',xobj_id=0,
        pdf_paragraph_composition=[PdfParagraphComposition(pdf_character=c) for c in glyphs])


def update():return object.__new__(ParagraphFinder).update_paragraph_data


def test_interleaved_modality_is_restored_in_reading_order_without_losing_glyphs():
    a=paragraph(chars('The peer ',0)+chars(' use TLS.',70));b=paragraph(chars('MUST',45))
    before=Counter(c.pdf_character.char_unicode for p in [a,b] for c in p.pdf_paragraph_composition)
    result,changes=merge_raw([a,b],update())
    assert len(result)==1 and 'The peer MUST use TLS.'==result[0].unicode
    assert Counter(c.pdf_character.char_unicode for p in result for c in p.pdf_paragraph_composition)==before
    assert len(changes)==1


def test_adjacent_columns_and_overprinted_duplicates_are_not_merged():
    a=paragraph(chars('Text in a column.',0));b=paragraph(chars('Text in another column.',300))
    result,changes=merge_raw([a,b],update());assert len(result)==2 and not changes
    a=paragraph(chars('The peer ',0)+chars(' use TLS.',70));b=paragraph(chars('The peer ',0))
    result,changes=merge_raw([a,b],update());assert len(result)==2 and not changes


def test_clipped_word_and_line_edges_recover_complete_sentence_without_glyph_loss():
    def p(text,x,y,label,layout):
        value=paragraph(chars(text,x,y));value.layout_label=label;value.layout_id=layout
        update()(value,update_unicode=True);return value
    parts=[p('This des',0,100,'fallback_line',45),p('ign ensures that it is',40,100,'plain text',15),
           p('a',155,100,'fallback_line',45),p('regular',0,84,'fallback_line',46),
           p('packet with a short header.',40,84,'plain text',15)]
    before=Counter(c.pdf_character.char_unicode for q in parts for c in q.pdf_paragraph_composition)
    result,changes=merge_raw(parts,update())
    assert len(result)==1 and result[0].unicode=='This design ensures that it is a regular packet with a short header.'
    assert Counter(c.pdf_character.char_unicode for q in result for c in q.pdf_paragraph_composition)==before
    assert any(c.get('kind')=='same_region_line' for c in changes)


def test_fallback_edges_do_not_bridge_table_cells_different_regions_or_ambiguous_gutters():
    a=paragraph(chars('Left paragraph',0));a.layout_id=1
    b=paragraph(chars('Right paragraph',100));b.layout_id=2
    fragment=paragraph(chars('edge',75));fragment.layout_label='fallback_line';fragment.layout_id=3
    result,changes=merge_raw([a,b,fragment],update());assert len(result)==3 and not changes
    a.layout_label='table';b.layout_label='table'
    result,changes=merge_raw([a,b,fragment],update());assert len(result)==3 and not changes


def test_isolated_bullets_split_items_but_keep_continuations_and_all_glyphs():
    from babelko.source_flow import split_bullet_lists
    glyphs=chars('First item requires care,',30,100)+chars('including its continuation.',30,84)+chars('Second item excludes loss.',30,68)
    para=paragraph(glyphs);para.layout_id=2;para.debug_id='items';update()(para,True)
    bullets=chars('◦',20,100)+chars('◦',20,68)
    result,changes=split_bullet_lists([para],bullets,update())
    assert len(result)==2 and len(changes)==1
    assert result[0].unicode=='First item requires care, including its continuation.'
    assert result[1].unicode=='Second item excludes loss.'
    assert Counter(c.pdf_character.char_unicode for p in result for c in p.pdf_paragraph_composition)==Counter(c.char_unicode for c in glyphs)
    assert len({p.debug_id for p in result})==2
    marker_paragraphs=[paragraph([c]) for c in bullets]
    result,changes=split_bullet_lists([para]+marker_paragraphs,[],update())
    assert len(result)==4 and len(changes)==1
    assert result[-2:]==marker_paragraphs
    # Symbol-font advance boxes can overlap body text while actual ink does not.
    for marker in bullets:marker.box=Box(20,marker.box.y,45,marker.box.y2)
    result,changes=split_bullet_lists([para],bullets,update())
    assert len(result)==2 and len(changes)==1
    grouped_markers=paragraph(bullets)
    result,changes=split_bullet_lists([para,grouped_markers],[],update())
    assert len(result)==3 and len(changes)==1 and result[-1] is grouped_markers


def test_single_bullets_math_dots_and_other_column_markers_do_not_split_prose():
    from babelko.source_flow import split_bullet_lists
    para=paragraph(chars('First sentence.',30,100)+chars('Second sentence.',30,84))
    for marks in [chars('◦',20,100),chars('.',20,100)+chars('.',20,84),chars('◦',320,100)+chars('◦',320,84)]:
        result,changes=split_bullet_lists([para],marks,update());assert result==[para] and not changes


def test_caption_closing_punctuation_stays_with_its_translated_caption():
    a=paragraph(chars('Table 1: Details (Continued',0));a.layout_label='table_caption';a.layout_id=3
    b=paragraph(chars(')',len('Table 1: Details (Continued')*5));b.layout_label='fallback_line';b.layout_id=4
    result,changes=merge_raw([a,b],update())
    assert len(result)==1 and result[0].unicode=='Table 1: Details (Continued)'
    assert result[0].layout_label=='table_caption'
