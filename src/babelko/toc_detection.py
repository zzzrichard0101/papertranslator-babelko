"""Find contents pages from repeated locator geometry, not one title language."""
import re
import statistics

from .region_ledger import characters
from .source_flow import lines

REVISION='geometric-contents-2'
TITLE=re.compile(r'contents|table\s+of\s+contents|sommaire|table\s+des\s+mati[eè]res|'
    r'inhaltsverzeichnis|[ií]ndice|sum[aá]rio|목\s*차|目次|目録|目錄|目录|目錄|содержание',re.I)
HEADING=re.compile(r'^(?:'+TITLE.pattern+r')(?:\s+(?:page|seite|p[aá]gina|페이지|頁|页))?$',re.I)
REFERENCE=re.compile(r'(?:\d{1,4}|[ivxlcdm]{1,8})$',re.I)
YEAR=re.compile(r'^(?:19|20)\d\d$')


def roman_value(value):
    values=dict(i=1,v=5,x=10,l=50,c=100,d=500,m=1000)
    total=0;previous=0
    for char in reversed(value.lower()):
        amount=values[char];total+=-amount if amount<previous else amount;previous=amount
    return total


def locator(row,width):
    """Return a terminal page reference only when it has a physical gutter."""
    visible=[c for c in row if c.box and (c.char_unicode or '').strip()]
    if not visible:return None
    tail=[visible[-1]]
    height=max(1,tail[0].box.y2-tail[0].box.y)
    if not re.fullmatch(r'[0-9ivxlcdm]',tail[0].char_unicode or '',re.I):return None
    for char in reversed(visible[:-1]):
        if (not re.fullmatch(r'[0-9ivxlcdm]',char.char_unicode or '',re.I)
                or tail[0].box.x-char.box.x2>max(4,height*.7)):break
        tail.insert(0,char)
    token=''.join(c.char_unicode or '' for c in tail)
    if not REFERENCE.fullmatch(token) or YEAR.fullmatch(token):return None
    first=min(c.box.x for c in tail);right=max(c.box.x2 for c in tail)
    if first<width*.34:return None
    label=[c for c in row if c.box and c.box.x2<first-2]
    label_ink=[c for c in label if (c.char_unicode or '').strip()]
    if label_ink:
        gap=first-max(c.box.x2 for c in label_ink)
        height=statistics.median(c.box.y2-c.box.y for c in label_ink)
        if gap<max(10,height*1.2):return None
        label_text=''.join(c.char_unicode or '' for c in label).strip()
        if len(re.findall(r'[^\W\d_]',label_text))<3:return None
    else:
        gap=0;label_text=''
        if any(c.box.x2<first-2 and (c.char_unicode or '').strip() for c in row):return None
    value=int(token) if token.isdigit() else roman_value(token)
    return dict(label=label,number=tail,label_text=label_text,reference=token,
        value=value,gap=gap,right=right,y=statistics.median((c.box.y+c.box.y2)/2 for c in tail))


def page_evidence(page):
    if not hasattr(page,'pdf_paragraph') or page.mediabox is None:
        return dict(candidates=[],title=False,clusters=[],inline=0,monotonic=0,
            label_ratio=0,gutter=0,indent_levels=0,diversity=0,selected=False,reason='no_il')
    width=page.mediabox.box.x2-page.mediabox.box.x
    texts=[re.sub(r'\s+',' ',p.unicode or '').strip() for p in page.pdf_paragraph]
    title=any(HEADING.fullmatch(value) for value in texts if len(value)<90)
    candidates=[]
    for paragraph in page.pdf_paragraph:
        for row in lines(list(characters(paragraph.pdf_paragraph_composition))):
            item=locator(row,width)
            if item:item=dict(item,paragraph=paragraph,row=row);candidates.append(item)
    tolerance=max(8,width*.025);clusters=[]
    for item in sorted(candidates,key=lambda r:r['right']):
        group=next((group for group in clusters if abs(statistics.median(v['right'] for v in group)-item['right'])<=tolerance),None)
        if group is None:clusters.append([item])
        else:group.append(item)
    clusters.sort(key=len,reverse=True)
    primary=clusters[0] if clusters else []
    inline=[r for r in primary if r['label_text']]
    ordered=sorted(primary,key=lambda r:-r['y'])
    comparisons=[b['value']>=a['value'] for a,b in zip(ordered,ordered[1:])]
    monotonic=sum(comparisons)/len(comparisons) if comparisons else 0
    good_labels=sum(len(re.findall(r'\d+',r['label_text']))<=1 for r in inline)
    label_ratio=good_labels/max(1,len(inline))
    gutter=statistics.median(r['gap'] for r in inline) if inline else 0
    leaders=sum(bool(re.search(r'(?:\.{3,}|…{2,}|·{3,})',r['label_text'])) for r in inline)
    indents=len({round(min(c.box.x for c in r['label'] if c.box)/12) for r in inline})
    diversity=len({re.sub(r'\W+','',r['label_text']).lower() for r in inline})/max(1,len(inline))
    # A title is useful evidence but never the only condition. A titleless
    # contents page needs a stronger repeated, increasing locator pattern.
    titled=title and len(primary)>=3 and len(inline)>=2
    geometric=(len(primary)>=7 and len(inline)>=6 and monotonic>=.82 and label_ratio>=.8
        and diversity>=.75 and (leaders>=3 or indents>=2) and gutter>=width*.08
        and statistics.median(r['right'] for r in primary)>width*.65)
    return dict(candidates=candidates,title=bool(title),clusters=[len(c) for c in clusters],
        inline=len(inline),monotonic=round(monotonic,3),label_ratio=round(label_ratio,3),
        gutter=round(gutter,1),indent_levels=indents,diversity=round(diversity,3),selected=bool(titled or geometric),
        reason='title_and_locators' if titled else 'repeated_locators' if geometric else 'insufficient_evidence')


def classify(docs):
    pages=list(docs.page);reports=[page_evidence(page) for page in pages]
    # A continuation page can omit the heading or contain only a few entries.
    # Require both neighboring evidence and its own aligned locators.
    for index,report in enumerate(reports):
        if report['selected'] or not 3<=len(report['candidates'])<=6:continue
        if not any(0<=other<len(reports) and reports[other]['selected'] for other in (index-1,index+1)):continue
        if report['clusters'] and report['clusters'][0]>=3 and report['inline']>=2 and report['monotonic']>=.5:
            report['selected']=True;report['reason']='continuation'
    return reports
