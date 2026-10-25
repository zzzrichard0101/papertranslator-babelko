"""Check translated prose survives PDF export, separately from model verdicts."""
import re,unicodedata,collections,statistics
import pymupdf as fitz
from .storage import read

TOKENS=re.compile(r"\{v\d+\}|<style\s+id=['\"]\d+['\"]>|</style>")
REVISION='short-exact-2'


def canonical(text):
    return ''.join(c.lower() for c in unicodedata.normalize('NFKC',text) if c.isalnum())


def outputs(value):
    if isinstance(value,dict):
        if 'pdf_unicode' in value and value.get('input'):
            if isinstance(value.get('output'),str):yield value['output']
        else:
            for child in value.values():yield from outputs(child)
    elif isinstance(value,list):
        for child in value:yield from outputs(child)


def records(value):
    if isinstance(value,dict):
        if 'pdf_unicode' in value and value.get('input'):
            if isinstance(value.get('output'),str):yield value
        else:
            for child in value.values():yield from records(child)
    elif isinstance(value,list):
        for child in value:yield from records(child)


def spatial_text(page):
    """Rebuild visual rows when the PDF emits each Korean glyph separately."""
    chars=[]
    for block in page.get_text('rawdict')['blocks']:
        for line in block.get('lines',[]):
            for span in line.get('spans',[]):
                chars.extend((c['c'],c['bbox']) for c in span.get('chars',[]) if c.get('c'))
    if not chars:return ''
    height=statistics.median(max(1,b[3]-b[1]) for _,b in chars)
    rows=[]
    for char,b in sorted(chars,key=lambda item:(item[1][1]+item[1][3])/2):
        y=(b[1]+b[3])/2
        if rows and abs(y-rows[-1][0])<=height*.4:rows[-1][1].append((char,b))
        else:rows.append((y,[(char,b)]))
    return '\n'.join(''.join(c for c,_ in sorted(row,key=lambda item:item[1][0])) for _,row in rows)


class ExactEvidence:
    """Consume each extracted character at most once, even across page scopes."""
    def __init__(self,pages):
        self.pages=pages;self.offsets=[];offset=0
        for page in pages:self.offsets.append(offset);offset+=len(page)
        self.text=''.join(pages);self.used=bytearray(offset)

    def reserve(self,value,page):
        if not value:return False
        if page is None:haystack=self.text;offset=0
        else:haystack=self.pages[page];offset=self.offsets[page]
        start=0
        while (found:=haystack.find(value,start))>=0:
            begin=offset+found;end=begin+len(value)
            if not any(self.used[begin:end]):
                self.used[begin:end]=b'\1'*len(value)
                return True
            start=found+1
        return False


def short_evidence(page_text,spatial_pages,long_parts,short_parts):
    """Reserve whole long phrases before matching short, repeated fragments."""
    views=(ExactEvidence(page_text),ExactEvidence(spatial_pages))
    order=lambda item:(item[0] is None,-len(item[1]))
    for page,value in sorted(long_parts,key=order):
        for view in views:view.reserve(value,page)
    results=[False]*len(short_parts)
    # A one-syllable page-local fragment must not consume the only occurrence
    # of a longer cross-page phrase before that phrase gets matched. Prefer
    # specific evidence first; use page scope only to break equal-length ties.
    for ordinal,(index,page,value) in sorted(enumerate(short_parts),
            key=lambda item:(-len(item[1][2]),item[1][1] is None)):
        # Reserve the same evidence in both alternative extraction orders.
        results[ordinal]=any([view.reserve(value,page) for view in views])
    return results


def inspect(path,tracker,extracted_pages=None,source_path=None,ledger_path=None,selected=None):
    if extracted_pages is None:
        with fitz.open(path) as doc:
            page_text=[canonical(p.get_text()) for p in doc]
            spatial_pages=[canonical(spatial_text(p)) for p in doc]
    else:
        page_text=[canonical(t) for t in extracted_pages]
        with fitz.open(path) as doc:spatial_pages=[canonical(spatial_text(p)) for p in doc]
    tracked=read(tracker);page_map=isinstance(tracked,dict) and len(tracked.get('page',[]))==len(page_text)
    def counts(text):return collections.Counter(text[n:n+8] for n in range(len(text)-7))
    pools=[counts(t) for t in page_text];global_pool=counts(''.join(page_text))
    spatial_pools=[counts(t) for t in spatial_pages];spatial_global=counts(''.join(spatial_pages));items=[]
    if page_map:
        for i,page in enumerate(tracked['page']):items.extend((i,r) for r in records(page))
        for name in ['cross_page','cross_column']:items.extend((None,r) for r in records(tracked.get(name,[])))
    else:items=[(None,r) for r in records(tracked)]
    hidden=collections.Counter()
    if source_path is not None and ledger_path is not None and selected is not None:
        from .region_ledger import visible_in_crop
        source_pages={source+1:target for target,source in enumerate(selected)}
        with fitz.open(source_path) as original:
            for row in read(ledger_path).get('regions',[]):
                page=source_pages.get(row['source_page'])
                if page is None or visible_in_crop(row.get('source_box'),original[row['source_page']-1]):continue
                hidden[(page,canonical(row['source']),canonical(TOKENS.sub('',row.get('target') or '')))]+=1
    checked=0;matches=0;total=0;missing=[];page_checked=0
    long_parts=[];short_parts=[];short_units=set()
    for index,(page,record) in enumerate(items):
        target=record['output']
        key=(page,canonical(record['pdf_unicode']),canonical(TOKENS.sub('',target)))
        if hidden[key]:hidden[key]-=1;continue
        grams=[]
        for part in TOKENS.split(target):
            hangul=len(re.findall('[가-힣]',part))
            if not hangul:continue
            value=canonical(part)
            if not value:continue
            if hangul<8:
                short_parts.append((index,page,value));short_units.add(index)
                continue
            long_parts.append((page,value))
            grams.extend(value[n:n+8] for n in range(len(value)-7))
        if not grams:
            if index in short_units:
                checked+=1
                if page is not None:page_checked+=1
            continue
        checked+=1;pool=pools[page] if page is not None else global_pool
        spatial_pool=spatial_pools[page] if page is not None else spatial_global
        if page is not None:page_checked+=1
        needed=collections.Counter(grams)
        found=max(sum(min(pool[g],n) for g,n in needed.items()),
            sum(min(spatial_pool[g],n) for g,n in needed.items()))
        for g,n in needed.items():pool[g]=max(0,pool[g]-n)
        for g,n in needed.items():spatial_pool[g]=max(0,spatial_pool[g]-n)
        matches+=found;total+=len(grams)
        if found/len(grams)<.75:missing.append(dict(tracked_unit=index,page=page+1 if page is not None else None,matched=found,expected=len(grams),target_excerpt=target[:140]))
    exact=short_evidence(page_text,spatial_pages,long_parts,short_parts)
    for (index,page,value),found in zip(short_parts,exact):
        if not found:
            missing.append(dict(tracked_unit=index,page=page+1 if page is not None else None,
                code='short_text_missing',expected_text=value[:80],target_excerpt=items[index][1]['output'][:140]))
    return dict(revision=REVISION,status='failed' if missing else 'passed',checked_prose_units=checked,
        page_checked_units=page_checked,page_mapping_available=page_map,
        checked_short_fragments=len(short_parts),missing_short_fragments=sum(r.get('code')=='short_text_missing' for r in missing),
        matched_ngrams=matches,expected_ngrams=total,missing=missing,
        scope='Long Korean prose uses n-grams; short fragments use exact, non-overlapping occurrences after whole long phrases. Page tracking where available; cross-page/column groups use global text. Not exact placement or OCR recall.')
