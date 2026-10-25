"""Expose prose dates/ordinals incorrectly isolated as mathematical typography."""
import collections,copy,re,unicodedata
from contextlib import contextmanager
from unittest.mock import patch

MONTH=r'(?:January|February|March|April|May|June|July|August|September|October|November|December)'


def merge_hyphenated_fallbacks(docs):
    """Rejoin a word split by line-level layout fallback, within one column."""
    changes=[]
    for page in docs.page:
        paragraphs=getattr(page,'pdf_paragraph',[]);removed=set()
        for left in sorted(paragraphs,key=lambda p:(-p.box.y2,p.box.x) if p.box else (0,0)):
            if id(left) in removed or left.layout_label!='fallback_line' or not left.box:continue
            while re.search(r'[A-Za-z]{2,}[-\u00ad]\s*$',left.unicode or ''):
                size=(left.pdf_style.font_size if left.pdf_style else None) or left.box.y2-left.box.y
                candidates=[]
                for right in paragraphs:
                    if right is left or id(right) in removed or right.layout_label!='fallback_line' or not right.box:continue
                    if left.xobj_id!=right.xobj_id or not re.match(r'[a-z]{2,}',right.unicode or ''):continue
                    gap=left.box.y-right.box.y2;overlap=min(left.box.x2,right.box.x2)-max(left.box.x,right.box.x)
                    if -.1*size<=gap<=size*.9 and abs(left.box.x-right.box.x)<=size*1.5 and overlap>=.75*min(left.box.x2-left.box.x,right.box.x2-right.box.x):candidates.append((gap,right))
                if len(candidates)!=1:break
                right=candidates[0][1];before=[left.unicode,right.unicode]
                left.pdf_paragraph_composition.extend(right.pdf_paragraph_composition)
                left.unicode=left.unicode.rstrip()+' '+right.unicode.lstrip()
                left.box.y=min(left.box.y,right.box.y);left.box.y2=max(left.box.y2,right.box.y2)
                left.box.x=min(left.box.x,right.box.x);left.box.x2=max(left.box.x2,right.box.x2)
                removed.add(id(right));changes.append(dict(page=getattr(page,'page_number',None),before=before,after=left.unicode))
        if removed:page.pdf_paragraph=[p for p in paragraphs if id(p) not in removed]
    return changes


def expose_prose_formulas(docs):
    """Small-caps running titles can be misclassified as entirely mathematical."""
    from babeldoc.format.pdf.document_il import PdfLine,PdfParagraphComposition
    from babeldoc.format.pdf.document_il.utils.layout_helper import get_char_unicode_string
    from babeldoc.format.pdf.document_il.utils.paragraph_helper import is_placeholder_only_paragraph
    changes=[]
    for page in docs.page:
        paragraphs=getattr(page,'pdf_paragraph',[]);removed=set();groups=[]
        opaque=[p for p in paragraphs if p.box and is_placeholder_only_paragraph(p)]
        for p in sorted(opaque,key=lambda p:(-p.box.y2,p.box.x)):
            candidates=[]
            for group in groups:
                left=group[-1];size=(left.pdf_style.font_size if left.pdf_style else None) or 10
                overlap=min(left.box.y2,p.box.y2)-max(left.box.y,p.box.y)
                if left.xobj_id==p.xobj_id and 0<=p.box.x-left.box.x2<=size*.7 and overlap>=.45*min(left.box.y2-left.box.y,p.box.y2-p.box.y):candidates.append(group)
            if len(candidates)==1:candidates[0].append(p)
            else:groups.append([p])
        for group in groups:
            chars=[]
            for p in group:
                for c in p.pdf_paragraph_composition:
                    if c.pdf_formula:chars.extend(c.pdf_formula.pdf_character)
                    elif c.pdf_character:chars.append(c.pdf_character)
            if not chars:continue
            text=get_char_unicode_string(chars);words=re.findall(r'[A-Za-z]+',text)
            compact=re.sub(r'\s','',text)
            if len(words)<6 or sum(w.lower() in {'a','an','the','of','in','to','for','with','and','on','is','are'} for w in words)<2:continue
            if sum(c.isascii() and c.isalpha() for c in compact)/max(1,len(compact))<.75 or re.search(r'[=∑∫∂≤≥<>]',text):continue
            left=group[0];before=[p.unicode for p in group]
            if left.pdf_style is None:
                styles=[c.pdf_style for c in chars if c.pdf_style is not None]
                if not styles:continue
                counts=collections.Counter((s.font_id,s.font_size) for s in styles)
                dominant=counts.most_common(1)[0][0]
                # IL styles may retain deeply nested parser state. Only the
                # top-level style is ever mutated here; copying its graph can
                # overflow Python's recursion limit on otherwise valid PDFs.
                left.pdf_style=copy.copy(next(s for s in styles if (s.font_id,s.font_size)==dominant))
            left.box.x=min(p.box.x for p in group);left.box.x2=max(p.box.x2 for p in group)
            left.box.y=min(p.box.y for p in group);left.box.y2=max(p.box.y2 for p in group)
            left.pdf_paragraph_composition=[PdfParagraphComposition(pdf_line=PdfLine(box=copy.copy(left.box),pdf_character=chars))]
            left.unicode=text;removed.update(id(p) for p in group[1:])
            changes.append(dict(page=getattr(page,'page_number',None),before=before,after=text))
        if removed:page.pdf_paragraph=[p for p in paragraphs if id(p) not in removed]
    return changes


def caption_word_repairs(docs):
    """Repair split words only with repeated vocabulary evidence in this PDF."""
    counts=collections.Counter(w.lower() for page in docs.page for p in page.pdf_paragraph for w in re.findall(r'[A-Za-z]{3,}',p.unicode or ''))
    repairs={}
    for page in docs.page:
        captions=sorted([p for p in page.pdf_paragraph if p.layout_label=='figure_caption' and p.box and p.unicode],key=lambda p:(-p.box.y2,p.box.x))
        pairs=[(left,right) for left in captions for right in captions if left is not right]
        candidates=collections.defaultdict(list)
        for left,right in pairs:
            a=re.search(r'([A-Za-z]{6,})\s*$',left.unicode);b=re.match(r'\s*([A-Za-z]{3,})',right.unicode)
            if not a or not b or counts[a[1].lower()]>2:continue
            height=max((left.pdf_style.font_size or 10) if left.pdf_style else 10,(right.pdf_style.font_size or 10) if right.pdf_style else 10)
            gap=left.box.y-right.box.y2
            overlap=min(left.box.x2,right.box.x2)-max(left.box.x,right.box.x)
            vertical=min(left.box.y2,right.box.y2)-max(left.box.y,right.box.y)
            inline=vertical>min(left.box.y2-left.box.y,right.box.y2-right.box.y)*.4 and -height*.5<=right.box.x-left.box.x2<=height*4
            nextline=-height<=gap<=height*2 and overlap>0
            if not (inline or nextline):continue
            choices=[]
            for n in range(2,min(5,len(a[1])-2)):
                prefix,joined=a[1][:-n],a[1][-n:]+b[1]
                if counts[prefix.lower()]>=2 and counts[joined.lower()]>=2:choices.append((prefix,joined))
            if len(choices)!=1:continue
            prefix,joined=choices[0]
            candidates[left.debug_id].append((right.debug_id,a[1],prefix,b[1],joined))
        for key,values in candidates.items():
            if len(values)!=1:continue
            other,old,prefix,head,joined=values[0]
            repairs[key]=dict(end=(old,prefix));repairs[other]=dict(start=(head,joined))
    return repairs


def cross_boundary_word_repairs(docs):
    """Move a split word to the following text unit before model inference.

    The source glyphs and page geometry remain untouched. This only changes
    the two model inputs, so neither model sees an invented half-word such as
    ``mary`` from ``In sum-`` / ``mary`` at a column boundary.
    """
    repairs={};candidates=[]
    for page in docs.page:
        for paragraph in getattr(page,'pdf_paragraph',[]):
            if paragraph.layout_label in {'plain text','text','paragraph_hybrid'} and paragraph.unicode:
                candidates.append((page.page_number,paragraph))
    for (left_page,left),(right_page,right) in zip(candidates,candidates[1:]):
        if right_page-left_page not in {0,1}:continue
        # OCR/PDF extraction can glue preceding words to the split word
        # ("domainsviacoordinatetransfor-" / "mations"). Moving the
        # complete tail is safer than asking the model to invent a meaning
        # for an isolated suffix.
        a=re.search(r'([A-Za-z]{2,40})-\s*$',left.unicode)
        b=re.match(r'\s*([a-z]{2,10})\b',right.unicode)
        if not a or not b:continue
        joined=a[1]+b[1]
        if len(joined)>48:continue
        before=left.unicode[:a.start()]
        lead=re.search(r'(?i)\b(By|In|For|To|With|Without|After|Before|While|Although)\s+$',before)
        prefix=before[lead.start():] if lead else ''
        tail=prefix+a[0].rstrip()
        replacement=prefix+joined
        repairs.setdefault(left.debug_id,{})['cross_end']=tail
        repairs.setdefault(right.debug_id,{})['cross_start']=(b[1],replacement)
    return repairs


def repair_caption_input(value,repair):
    if value is None:return value
    if 'end' in repair:
        old,new=repair['end'];value.unicode=re.sub(re.escape(old)+r'(?=(?:</style>)*\s*$)',new,value.unicode)
    if 'start' in repair:
        old,new=repair['start'];value.unicode=re.sub(r'^(\s*(?:<style\s+id=[\'\"]\d+[\'\"]>)*)'+re.escape(old),lambda m:m[1]+new,value.unicode)
    if 'cross_end' in repair:
        tail=repair['cross_end']
        value.unicode=re.sub(re.escape(tail)+r'(?=(?:</style>)*\s*$)','',value.unicode)
    if 'cross_start' in repair:
        old,new=repair['cross_start']
        value.unicode=re.sub(r'^(\s*(?:<style\s+id=[\'\"]\d+[\'\"]>)*)'+re.escape(old),lambda m:m[1]+new,value.unicode)
    return value


def normalize_input(value):
    if value is None:return value
    from babeldoc.format.pdf.document_il.midend.il_translator import FormulaPlaceholder,RichTextPlaceholder
    for placeholder in list(value.placeholders):
        if isinstance(placeholder,FormulaPlaceholder):
            chars=placeholder.formula.pdf_character
            text=unicodedata.normalize('NFKC',''.join(c.char_unicode or '' for c in chars)).strip()
            match=re.fullmatch(r'([•●▪◦]\s*)(\d{1,2})',text)
            # A day before a named month is prose, not an opaque equation. Keep
            # the bullet glyph while exposing its grouped day for Korean order.
            if not match or not 1<=int(match[2])<=31:continue
            following=value.unicode.split(placeholder.placeholder,1)[-1]
            if not re.match(r'\s*'+MONTH+r'\s+\d{4}\b',following,re.I):continue
            retained=[copy.copy(c) for c in chars if not any(ch.isdigit() for ch in (c.char_unicode or ''))]
            if not retained:continue
            replacement=copy.copy(placeholder);replacement.formula=copy.copy(placeholder.formula)
            replacement.formula.box=copy.copy(placeholder.formula.box)
            replacement.formula.pdf_character=retained
            boxes=[c.box for c in retained if c.box is not None]
            if boxes:
                box=replacement.formula.box
                box.x=min(b.x for b in boxes);box.x2=max(b.x2 for b in boxes)
                box.y=min(b.y for b in boxes);box.y2=max(b.y2 for b in boxes)
            value.placeholders[value.placeholders.index(placeholder)]=replacement
            value.unicode=value.unicode.replace(placeholder.placeholder,placeholder.placeholder+match[2]+' ',1)
        elif isinstance(placeholder,RichTextPlaceholder):
            suffix=''.join(c.char_unicode or '' for c in (placeholder.composition.pdf_character or []))
            if suffix not in {'st','nd','rd','th'}:continue
            marked=placeholder.left_placeholder+suffix+placeholder.right_placeholder
            pattern=r'(?<=\d)'+re.escape(marked)+r'(?=\s+[A-Za-z]{2,})'
            if not re.search(pattern,value.unicode):continue
            # The suffix font is not meaningful in Korean. Flatten this one
            # ordinal into normal prose, retaining all other rich styles/math.
            value.unicode=re.sub(pattern,suffix,value.unicode)
            value.placeholders.remove(placeholder)
    return value


@contextmanager
def prose_structure(repairs=None,scan_plans=None,source_repair=None):
    from babeldoc.format.pdf.document_il.midend.il_translator import ILTranslator
    original=ILTranslator.get_translate_input
    def adapted(self,*args,**kwargs):
        value=normalize_input(original(self,*args,**kwargs))
        paragraph=args[0] if args else kwargs['paragraph']
        value=repair_caption_input(value,(repairs or {}).get(paragraph.debug_id,{}))
        item=(scan_plans or {}).get(paragraph.debug_id)
        if value is not None and item:
            original_text=value.unicode
            changes=[]
            if item.get('recovery'):
                value,recovered=item['recovery'](value,paragraph,item)
                changes.extend(recovered)
            from .scan_evidence import normalize_input as normalize_scan
            before,changed,edits=normalize_scan(value,item)
            if edits:
                value.unicode=changed
                changes.extend(edits)
            if changes and source_repair and value.unicode!=original_text:
                source_repair(original_text,value.unicode,changes)
        return value
    with patch.object(ILTranslator,'get_translate_input',adapted):yield
