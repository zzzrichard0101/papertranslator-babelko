"""Split detected contents rows while preserving every source character."""
import collections
import copy
import re

from .region_ledger import characters
from .source_flow import lines
from .toc_detection import REVISION,classify,locator,TITLE

TEXT_LABELS={'text','plain text','paragraph_hybrid','fallback_line','abandon'}
PAGE_HEADER=re.compile(r'page|seite|p[aá]gina|페이지|頁|页|стр\.?',re.I)


def header_parts(row,width):
    visible=[c for c in row if c.box and (c.char_unicode or '').strip()]
    right=[c for c in visible if c.box.x>width*.7]
    if not right or not PAGE_HEADER.fullmatch(''.join(c.char_unicode or '' for c in right)):return None
    left=[c for c in row if c.box and c.box.x2<right[0].box.x-2]
    if not TITLE.search(''.join(c.char_unicode or '' for c in left)):return None
    return [('entry',left),('header',right)]


def new_piece(paragraph,group,role,index,row_index,number_start=None):
    from babeldoc.format.pdf.document_il import PdfLine,PdfParagraphComposition
    item=copy.copy(paragraph)
    item.debug_id=(paragraph.debug_id or 'toc')+f'-toc-{index}-{row_index}-{role}'
    item.box=copy.copy(paragraph.box)
    ink=[c for c in group if (c.char_unicode or '').strip()] or group
    item.box.x=min(c.box.x for c in ink);item.box.x2=max(c.box.x2 for c in ink)
    item.box.y=min(c.box.y for c in ink);item.box.y2=max(c.box.y2 for c in ink)
    if role=='entry' and number_start is not None:item.box.x2=max(item.box.x2,number_start-12)
    item.pdf_paragraph_composition=[PdfParagraphComposition(pdf_line=PdfLine(
        box=copy.copy(item.box),pdf_character=group))]
    item.unicode=''.join(c.char_unicode or '' for c in group).strip()
    item.layout_label='fallback_line' if role in {'number','header'} else paragraph.layout_label
    return item


def conserved(paragraph,pieces):
    def ink(value):
        # Compare source glyph identity, including punctuation and symbols.
        # Whitespace can be normalized by the layout engine.
        glyphs=[]
        for composition in value.pdf_paragraph_composition:
            if composition.pdf_line is not None:glyphs.extend(composition.pdf_line.pdf_character)
            elif composition.pdf_character is not None:glyphs.append(composition.pdf_character)
            else:glyphs.extend(characters(composition))
        return collections.Counter(id(char) for char in glyphs
            if (char.char_unicode or '').strip())
    return ink(paragraph)==sum((ink(piece) for piece in pieces),collections.Counter())


def recover_omitted_characters(paragraph,pieces):
    """Reattach dropped source glyphs to the nearest row, then recheck."""
    used={id(c) for piece in pieces for c in characters(piece.pdf_paragraph_composition)}
    omitted=[c for c in characters(paragraph.pdf_paragraph_composition)
        if id(c) not in used and c.box and (c.char_unicode or '').strip()]
    for char in omitted:
        x=(char.box.x+char.box.x2)/2;y=(char.box.y+char.box.y2)/2
        piece=min(pieces,key=lambda p:(max(p.box.x-x,0,x-p.box.x2)**2+
            max(p.box.y-y,0,y-p.box.y2)**2))
        line=piece.pdf_paragraph_composition[0].pdf_line
        line.pdf_character.append(char)
        line.pdf_character.sort(key=lambda c:c.box.x)
        piece.unicode=''.join(c.char_unicode or '' for c in line.pdf_character).strip()
        piece.box.x=min(piece.box.x,char.box.x);piece.box.x2=max(piece.box.x2,char.box.x2)
        piece.box.y=min(piece.box.y,char.box.y);piece.box.y2=max(piece.box.y2,char.box.y2)
        line.box=copy.copy(piece.box)
    return len(omitted) if conserved(paragraph,pieces) else 0


def splittable(paragraph):
    if paragraph.layout_label not in TEXT_LABELS:return False
    # OCR also wraps short ordinary words as formulas. Rebuild text-only spans
    # from the original glyph objects, while leaving math/operators and shapes.
    for composition in paragraph.pdf_paragraph_composition:
        formula=composition.pdf_formula
        if formula is not None:
            glyphs=formula.pdf_character or []
            text=''.join(c.char_unicode or '' for c in glyphs)
            if (not glyphs or formula.pdf_curve or formula.pdf_form or
                    any(c in text for c in '=∑∫√≤≥≈≠±×÷^')):return False
    return True


def split_rows(docs,diagnostics=None):
    decisions=classify(docs);changes=[];pages=[]
    for page_index,(page,decision) in enumerate(zip(docs.page,decisions)):
        report={key:value for key,value in decision.items() if key!='candidates'}
        report.update(page=page_index+1,split_paragraphs=0,split_entries=0,
            recovered_characters=0,restored_paragraphs=0)
        pages.append(report)
        if not decision['selected']:continue
        width=page.mediabox.box.x2-page.mediabox.box.x
        output=[]
        for index,paragraph in enumerate(page.pdf_paragraph):
            if not splittable(paragraph):
                output.append(paragraph);continue
            rows=lines(list(characters(paragraph.pdf_paragraph_composition)))
            if not rows:
                output.append(paragraph);continue
            pieces=[];paired=[]
            for row_index,row in enumerate(rows):
                found=locator(row,width)
                if found and found['label_text']:
                    groups=[('entry',found['label']),('number',found['number'])]
                else:groups=header_parts(row,width) or [('entry',row)]
                if len(rows)==1 and len(groups)==1:pieces=[paragraph];break
                number_start=groups[1][1][0].box.x if len(groups)==2 else None
                items=[new_piece(paragraph,group,role,index,row_index,number_start) for role,group in groups]
                pieces.extend(items)
                if len(groups)==2 and groups[1][0]=='number':paired.append((items[0],items[1]))
            if pieces==[paragraph]:output.append(paragraph);continue
            if len(pieces)>1 and not conserved(paragraph,pieces):
                report['recovered_characters']+=recover_omitted_characters(paragraph,pieces)
            valid=(len(pieces)>1 and conserved(paragraph,pieces) and all(
                entry.box.x2+5<=number.box.x and
                abs((entry.box.y+entry.box.y2-number.box.y-number.box.y2)/2)<=max(12,entry.box.y2-entry.box.y)
                for entry,number in paired))
            if not valid:
                output.append(paragraph);report['restored_paragraphs']+=1;continue
            output.extend(pieces);report['split_paragraphs']+=1;report['split_entries']+=len(paired)
            changes.append(dict(page=page_index+1,before=paragraph.unicode,
                after=[p.unicode for p in pieces]))
        page.pdf_paragraph=output
    if diagnostics is not None:
        unresolved=[dict(page=p['page'],detected=p['inline'],split=p['split_entries'])
            for p in pages if p['selected'] and p['split_entries']<p['inline']]
        diagnostics.update(revision=REVISION,status='passed' if not unresolved else 'incomplete',
            pages=pages,selected_pages=[p['page'] for p in pages if p['selected']],
            unresolved_pages=unresolved,restored_paragraphs=sum(p['restored_paragraphs'] for p in pages))
    return changes
