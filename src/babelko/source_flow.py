"""Reunite interleaved font/color runs BEFORE native formula/style analysis."""
import copy,statistics
from contextlib import contextmanager
from unittest.mock import patch
from .storage import save

TEXT_LABELS={'text','plain text','paragraph_hybrid','abandon','fallback_line'}


def raw_chars(paragraph):
    comps=paragraph.pdf_paragraph_composition
    if not comps or any(c.pdf_character is None for c in comps):return None
    chars=[c.pdf_character for c in comps]
    if any(c.vertical or c.box is None for c in chars):return None
    return chars


def lines(chars):
    if not chars:return []
    height=statistics.median(c.box.y2-c.box.y for c in chars if c.box.y2>c.box.y) if any(c.box.y2>c.box.y for c in chars) else 10
    groups=[]
    for c in sorted(chars,key=lambda c:-(c.box.y+c.box.y2)/2):
        cy=(c.box.y+c.box.y2)/2
        if groups and abs(cy-groups[-1][0])<=height*.55:groups[-1][1].append(c)
        else:groups.append((cy,[c]))
    return [sorted(group,key=lambda c:c.box.x) for _,group in groups]


def interleaved(a,b):
    """A-B-A runs on a shared baseline, without duplicate overprinted glyphs."""
    labels={id(c):0 for c in a};labels.update({id(c):1 for c in b})
    small=b if len(b)<=len(a) else a;large=a if small is b else b
    for c in small:
        if any(c.char_unicode==d.char_unicode and abs(c.box.x-d.box.x)<.3 and abs(c.box.y-d.box.y)<.3 for d in large):
            # Conservatively leave overprinted/shadow text unchanged.
            return False
    for line in lines(a+b):
        visible=[c for c in line if (c.char_unicode or '').strip()]
        runs=[]
        for c in visible:
            label=labels[id(c)]
            if not runs or runs[-1][0]!=label:runs.append((label,[c]))
            else:runs[-1][1].append(c)
        for left,middle,right in zip(runs,runs[1:],runs[2:]):
            if left[0]!=right[0]:continue
            before,first=left[1][-1],middle[1][0];last,after=middle[1][-1],right[1][0]
            size=max((c.pdf_style.font_size or 10) if c.pdf_style else 10 for c in [before,first,last,after])
            if -.5<=first.box.x-before.box.x2<=size*1.6 and -.5<=after.box.x-last.box.x2<=size*1.6:return True
    return False


def join_fallback_edges(paragraphs,update):
    """Reattach short line fragments clipped by a text-layout boundary.

    A fallback may touch only one text region. Once attached, adjacent pieces
    of that SAME region can rejoin across a line break. This never bridges two
    different detected text regions, table cells, or a column gutter.
    """
    changes=[];removed=set();touched=set()
    anchors=[p for p in paragraphs if p.layout_label in (TEXT_LABELS-{'fallback_line'})|{'table_caption','figure_caption'} and p.layout_id is not None and raw_chars(p)]
    fragments=[p for p in paragraphs if p.layout_label=='fallback_line' and raw_chars(p) and len(raw_chars(p))<=48]
    def attach(base,other,kind):
        a,b=raw_chars(base),raw_chars(other)
        from babeldoc.format.pdf.document_il import PdfParagraphComposition
        from babeldoc.format.pdf.document_il.utils.layout_helper import get_char_unicode_string
        before=[get_char_unicode_string(a),get_char_unicode_string(b)]
        ordered=[c for line in lines(a+b) for c in line]
        base.pdf_paragraph_composition=[PdfParagraphComposition(pdf_character=c) for c in ordered]
        update(base,update_unicode=True);removed.add(id(other));touched.add(id(base))
        changes.append(dict(kind=kind,before=before,after=base.unicode))
    # A connected series can have more than one short edge fragment.
    for _ in range(len(fragments)):
        progress=False
        for fragment in fragments:
            if id(fragment) in removed:continue
            candidates=[]
            for base in anchors:
                if id(base) in removed or base.xobj_id!=fragment.xobj_id:continue
                a,b=raw_chars(base),raw_chars(fragment)
                for line in lines(a):
                    edge=min(b,key=lambda c:c.box.x);end=max(b,key=lambda c:c.box.x2)
                    first,last=line[0],line[-1]
                    size=statistics.median((c.pdf_style.font_size or 10) if c.pdf_style else 10 for c in line)
                    if abs(statistics.median(c.box.y for c in line)-statistics.median(c.box.y for c in b))>size*.25:continue
                    if any(c.pdf_style is None or abs((c.pdf_style.font_size or size)-size)>size*.15 for c in b):continue
                    gap=min(abs(first.box.x-end.box.x2),abs(edge.box.x-last.box.x2))
                    disjoint=end.box.x2<=first.box.x+.3 or edge.box.x>=last.box.x2-.3
                    if disjoint and gap<=size*.8:candidates.append(base);break
            # Multiple regions around a fragment are ambiguous: preserve it.
            if len(candidates)==1:attach(candidates[0],fragment,'fallback_edge');progress=True
        if not progress:break
    for base in anchors:
        if id(base) not in touched or id(base) in removed:continue
        while True:
            candidates=[]
            size=statistics.median((c.pdf_style.font_size or 10) if c.pdf_style else 10 for c in raw_chars(base))
            for other in anchors:
                if other is base or id(other) in removed or other.layout_id!=base.layout_id or other.xobj_id!=base.xobj_id:continue
                gap=max(base.box.y,other.box.y)-min(base.box.y2,other.box.y2)
                overlap=min(base.box.x2,other.box.x2)-max(base.box.x,other.box.x)
                if 0<=gap<=size*.9 and overlap>=.6*min(base.box.x2-base.box.x,other.box.x2-other.box.x):candidates.append(other)
            if len(candidates)!=1:break
            attach(base,candidates[0],'same_region_line')
    return [p for p in paragraphs if id(p) not in removed],changes


def merge_raw(paragraphs,update):
    """Merge only embedded, interleaved runs; never bridge columns or cells."""
    chars={id(p):raw_chars(p) for p in paragraphs};removed=set();changes=[]
    for base in sorted(paragraphs,key=lambda p:len(chars[id(p)] or []),reverse=True):
        if id(base) in removed or base.box is None or base.layout_label not in TEXT_LABELS or not chars[id(base)]:continue
        for other in paragraphs:
            if other is base or id(other) in removed or other.box is None or other.layout_label not in TEXT_LABELS:continue
            a,b=chars[id(base)],chars[id(other)]
            if not b or base.xobj_id!=other.xobj_id:continue
            x0=max(base.box.x,other.box.x);x1=min(base.box.x2,other.box.x2)
            y0=max(base.box.y,other.box.y);y1=min(base.box.y2,other.box.y2)
            minimum=min((base.box.x2-base.box.x)*(base.box.y2-base.box.y),(other.box.x2-other.box.x)*(other.box.y2-other.box.y))
            if minimum<=0 or max(0,x1-x0)*max(0,y1-y0)<minimum*.65:continue
            size=statistics.median((c.pdf_style.font_size or 10) if c.pdf_style else 10 for c in a)
            if any(c.box.y<base.box.y-size*.5 or c.box.y2>base.box.y2+size*.5 or c.box.x<base.box.x-size*4 or c.box.x2>base.box.x2+size*4 for c in b):continue
            if not interleaved(a,b):continue
            from babeldoc.format.pdf.document_il import PdfParagraphComposition
            from babeldoc.format.pdf.document_il.utils.layout_helper import get_char_unicode_string
            before=[get_char_unicode_string(a),get_char_unicode_string(b)]
            ordered=[c for line in lines(a+b) for c in line]
            base.pdf_paragraph_composition=[PdfParagraphComposition(pdf_character=c) for c in ordered]
            chars[id(base)]=ordered;removed.add(id(other));update(base,update_unicode=True)
            changes.append(dict(before=before,after=base.unicode))
    result,edges=join_fallback_edges([p for p in paragraphs if id(p) not in removed],update)
    return result,changes+edges


def split_bullet_lists(paragraphs,orphans,update):
    """Keep list items at their own rows when markers were isolated as math.

    Markers remain original glyphs. Only a paragraph with at least two uniquely
    matched, nearby left-hand bullet markers is split; continuation rows stay
    with their item. Ordinary dots, equations and neighboring columns do not
    provide evidence for a split.
    """
    from babeldoc.format.pdf.document_il import PdfParagraphComposition
    markers={'•','◦','▪','●','‣','⁃'}
    candidates=list(orphans)
    for paragraph in paragraphs:
        chars=raw_chars(paragraph)
        if chars and all(not (c.char_unicode or '').strip() or (c.char_unicode or '').strip() in markers for c in chars):candidates.extend(chars)
    bullets=[c for c in candidates if (c.char_unicode or '').strip() in markers and c.box and not c.vertical]
    def ink(char):return char.visual_bbox.box if char.visual_bbox and char.visual_bbox.box else char.box
    result=[];changes=[]
    for paragraph in paragraphs:
        chars=raw_chars(paragraph)
        if not chars or paragraph.layout_label not in TEXT_LABELS-{'fallback_line'}:result.append(paragraph);continue
        rows=lines(chars);starts=[]
        for index,row in enumerate(rows):
            visible=[c for c in row if (c.char_unicode or '').strip()]
            if not visible:continue
            first=visible[0];size=(first.pdf_style.font_size or 10) if first.pdf_style else 10
            matching=[b for b in bullets if b.xobj_id==paragraph.xobj_id and -.2<=ink(first).x-ink(b).x2<=size*1.5 and
                      ink(first).y<=((ink(b).y+ink(b).y2)/2)<=ink(first).y2]
            if len(matching)==1:starts.append(index)
        if len(starts)<2:result.append(paragraph);continue
        boundaries=sorted(set([0]+starts+[len(rows)]));pieces=[]
        for start,end in zip(boundaries,boundaries[1:]):
            item=copy.copy(paragraph)
            item.debug_id=(paragraph.debug_id or 'source')+'-list-'+str(start)
            item.pdf_paragraph_composition=[PdfParagraphComposition(pdf_character=c) for row in rows[start:end] for c in row]
            update(item,update_unicode=True);pieces.append(item)
        result.extend(pieces)
        changes.append(dict(kind='bullet_list',before=paragraph.unicode,after=[p.unicode for p in pieces]))
    return result,changes


@contextmanager
def source_flow(folder):
    from babeldoc.format.pdf.document_il.midend.paragraph_finder import ParagraphFinder
    original=ParagraphFinder._group_characters_into_paragraphs;changes=[]
    def grouped(self,page,*args,**kwargs):
        paragraphs=original(self,page,*args,**kwargs)
        result,repairs=merge_raw(paragraphs,self.update_paragraph_data)
        result,lists=split_bullet_lists(result,page.pdf_character,self.update_paragraph_data)
        changes.extend(dict(page=page.page_number,**r) for r in repairs+lists)
        save(folder/'source-flow-repairs.json',changes)
        return result
    with patch.object(ParagraphFinder,'_group_characters_into_paragraphs',grouped):yield
