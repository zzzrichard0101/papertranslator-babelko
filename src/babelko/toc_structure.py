"""Keep scanned contents entries on their physical rows before translation."""
import copy,re
from .storage import save


def composition_text(comp):
    run=getattr(comp,'pdf_same_style_characters',None) or getattr(comp,'pdf_formula',None)
    if run is None:return ''
    return ''.join(c.char_unicode or '' for c in run.pdf_character)


def contents_page(page):
    values=[re.sub(r'\s+',' ',p.unicode or '').strip() for p in page.pdf_paragraph]
    return (any(re.search(r'\bcontents\b',v,re.I) and len(v)<40 for v in values) and
        sum(len(re.findall(r'(?<!\d)\d{1,3}(?!\d)',v)) for v in values)>=8)


def split_paragraph(paragraph,page_width):
    comps=paragraph.pdf_paragraph_composition
    if len(comps)<6 or len(paragraph.unicode or '')<80 or len(re.findall(r'(?<!\d)\d{1,3}(?!\d)',paragraph.unicode or ''))<2:return None
    runs=[]
    for comp in comps:
        run=getattr(comp,'pdf_same_style_characters',None) or getattr(comp,'pdf_formula',None)
        if run is None or run.box is None or not run.pdf_character:return None
        text=composition_text(comp)
        if not text.strip():continue
        runs.append((comp,run.box,(run.box.y+run.box.y2)/2,text))
    if len(runs)<6:return None
    rows=[]
    for comp,box,center,value in sorted(runs,key=lambda item:(-item[2],item[1].x)):
        found=next((row for row in rows if abs(center-row[0])<=5),None)
        if found is None:rows.append([center,[(comp,box,value)]])
        else:found[1].append((comp,box,value))
    if len(rows)<2:return None
    pieces=[]
    for n,(_,items) in enumerate(rows):
        items.sort(key=lambda item:item[1].x)
        # Printed locator numbers remain visible in the source raster. Their
        # synthetic OCR boxes can extend beyond the physical page by hundreds
        # of points, and must not enlarge the translated title's text region.
        prose=[item for item in items if not (item[1].x>page_width*.78 and
            re.fullmatch(r'\s*\d{1,3}\s*',item[2]))]
        if not prose:continue
        text=' '.join(item[2].strip() for item in prose if item[2].strip())
        if not text:continue
        piece=copy.copy(paragraph);piece.debug_id=(paragraph.debug_id or 'toc')+'-row-'+str(n)
        piece.pdf_paragraph_composition=[item[0] for item in prose]
        piece.unicode=text;piece.box=copy.deepcopy(paragraph.box)
        piece.box.x=min(item[1].x for item in prose)
        piece.box.x2=min(page_width*.84,max(item[1].x2 for item in prose))
        piece.box.y=min(item[1].y for item in prose)
        piece.box.y2=max(item[1].y2 for item in prose)
        if piece.box.x2<=piece.box.x:continue
        pieces.append(piece)
    return pieces if len(pieces)>=2 else None


def split_contents(docs,folder):
    repairs=[]
    pages=list(docs.page);selected={i for i,page in enumerate(pages) if contents_page(page)}
    for i in list(selected):
        if i==0:continue
        previous=pages[i-1]
        numerals=sum(len(re.findall(r'(?<!\d)\d{1,3}(?!\d)',p.unicode or '')) for p in previous.pdf_paragraph)
        if numerals>=12:selected.add(i-1)
    for i,page in enumerate(pages):
        if i not in selected:continue
        new=[];page_width=page.cropbox.box.x2-page.cropbox.box.x
        for paragraph in page.pdf_paragraph:
            pieces=split_paragraph(paragraph,page_width)
            if pieces:
                repairs.append(dict(page=page.page_number+1,debug_id=paragraph.debug_id,
                    before=paragraph.unicode,after=[piece.unicode for piece in pieces]))
                new.extend(pieces)
            else:new.append(paragraph)
        page.pdf_paragraph=new
    save(folder/'source-contents-repairs.json',repairs)
    return repairs
