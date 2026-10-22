"""Check translated prose survives PDF export, separately from model verdicts."""
import re,unicodedata,collections
import pymupdf as fitz
from .storage import read

TOKENS=re.compile(r"\{v\d+\}|<style\s+id=['\"]\d+['\"]>|</style>")


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


def inspect(path,tracker,extracted_pages=None):
    if extracted_pages is None:
        with fitz.open(path) as doc:page_text=[canonical(p.get_text()) for p in doc]
    else:page_text=[canonical(t) for t in extracted_pages]
    tracked=read(tracker);page_map=isinstance(tracked,dict) and len(tracked.get('page',[]))==len(page_text)
    def counts(text):return collections.Counter(text[n:n+8] for n in range(len(text)-7))
    pools=[counts(t) for t in page_text];global_pool=counts(''.join(page_text));items=[]
    if page_map:
        for i,page in enumerate(tracked['page']):items.extend((i,t) for t in outputs(page))
        for name in ['cross_page','cross_column']:items.extend((None,t) for t in outputs(tracked.get(name,[])))
    else:items=[(None,t) for t in outputs(tracked)]
    checked=0;matches=0;total=0;missing=[];page_checked=0
    for index,(page,target) in enumerate(items):
        grams=[]
        for part in TOKENS.split(target):
            if len(re.findall('[가-힣]',part))<8:continue
            value=canonical(part)
            grams.extend(value[n:n+8] for n in range(len(value)-7))
        if not grams:continue
        checked+=1;pool=pools[page] if page is not None else global_pool
        if page is not None:page_checked+=1
        needed=collections.Counter(grams);found=sum(min(pool[g],n) for g,n in needed.items())
        for g,n in needed.items():pool[g]=max(0,pool[g]-n)
        matches+=found;total+=len(grams)
        if found/len(grams)<.75:missing.append(dict(tracked_unit=index,page=page+1 if page is not None else None,matched=found,expected=len(grams),target_excerpt=target[:140]))
    return dict(status='failed' if missing else 'passed',checked_prose_units=checked,
        page_checked_units=page_checked,page_mapping_available=page_map,
        matched_ngrams=matches,expected_ngrams=total,missing=missing,
        scope='Korean prose survival with multiplicity and page tracking where available; cross-page/column tracker groups use global text. Not exact placement or OCR recall.')
