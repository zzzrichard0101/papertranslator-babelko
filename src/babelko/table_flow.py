"""Recover coherent fallback prose inside cells bounded by repeated PDF rules."""
import collections,copy,re

ENTRY=re.compile(r'^\s*[A-Z][A-Z_ -]{2,}\s+\d+(?:\.\d+)*\s*:')


def cells(page):
    """Only repeated, segmented horizontal rules prove a column boundary."""
    if page.rotation or abs(page.cropbox.x0)>.1 or abs(page.cropbox.y0)>.1 or abs(page.mediabox.height-page.rect.height)>.1:return []
    rows=collections.defaultdict(list)
    for drawing in page.get_drawings():
        for item in drawing['items']:
            if item[0]!='l':continue
            a,b=item[1:]
            if abs(a.y-b.y)>.25 or abs(a.x-b.x)<20:continue
            rows[round((a.y+b.y)*1)/2].append((min(a.x,b.x),max(a.x,b.x)))
    patterns=collections.defaultdict(list)
    for y,segments in rows.items():
        chains=[]
        for a,b in sorted(segments):
            if chains and abs(chains[-1][-1]-a)<=.5:chains[-1].append(b)
            else:chains.append([a,b])
        for chain in chains:
            if len(chain)<3 or chain[-1]-chain[0]<120:continue
            key=tuple(round(x*2)/2 for x in chain)
            patterns[key].append(y)
    result=[]
    for edges,ys in patterns.items():
        if len(set(ys))<3:continue
        fences=sorted(set(page.rect.height-y for y in ys))
        for bottom,top in zip(fences,fences[1:]):
            for left,right in zip(edges,edges[1:]):
                if right-left>=30 and top-bottom>=10:result.append((left,bottom,right,top))
    return result


def merge_cells(paragraphs,regions,page_number=None):
    removed=set();changes=[]
    for x,y,x2,y2 in regions:
        parts=[p for p in paragraphs if id(p) not in removed and p.box and p.unicode and
               p.box.x>=x-1 and p.box.x2<=x2+1 and p.box.y>=y-1 and p.box.y2<=y2+1]
        # A detected native paragraph already provides stronger structure.
        if len(parts)<2 or any(p.layout_label!='fallback_line' for p in parts):continue
        groups=[]
        for p in sorted(parts,key=lambda p:(-p.box.y2,p.box.x)):
            size=(p.pdf_style.font_size if p.pdf_style else None) or 10
            if not groups or ENTRY.match(p.unicode) or groups[-1][-1].box.y-p.box.y2>size*.9:groups.append([p])
            else:groups[-1].append(p)
        for group in groups:
            if len(group)<2 or len(re.findall(r'[A-Za-z]+',' '.join(p.unicode for p in group)))<6:continue
            if len({p.xobj_id for p in group})!=1:continue
            # Same cell and aligned line starts, never neighboring subcolumns.
            if max(p.box.x for p in group)-min(p.box.x for p in group)>8:continue
            left=group[0];before=[p.unicode for p in group]
            weighted=[p for p in group if p.pdf_style is not None]
            if weighted:left.pdf_style=copy.deepcopy(max(weighted,key=lambda p:len(p.unicode)).pdf_style)
            left.pdf_paragraph_composition=[c for p in group for c in p.pdf_paragraph_composition]
            left.unicode=' '.join(before);left.layout_label='plain text'
            left.box=copy.deepcopy(left.box)
            left.box.x=min(p.box.x for p in group);left.box.x2=max(p.box.x2 for p in group)
            left.box.y=min(p.box.y for p in group);left.box.y2=max(p.box.y2 for p in group)
            removed.update(id(p) for p in group[1:])
            changes.append(dict(page=page_number,cell=[x,y,x2,y2],before=before,after=left.unicode))
    return [p for p in paragraphs if id(p) not in removed],changes


def merge_table_fallbacks(docs,path):
    import pymupdf as fitz
    changes=[]
    with fitz.open(path) as source:
        for page in docs.page:
            if page.page_number is None or not 0<=page.page_number<len(source):continue
            page.pdf_paragraph,repairs=merge_cells(page.pdf_paragraph,cells(source[page.page_number]),page.page_number)
            changes.extend(repairs)
    return changes
