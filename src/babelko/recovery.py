"""Bounded recovery of failed scan inputs from original pixels, never a target.

Cache OCR observations separately. Formula-rich native PDFs never enter this
path. A source change invalidates its translation key and semantic evidence.
"""
import difflib,hashlib,json,re,threading
from pathlib import Path
import pymupdf as fitz
from .storage import read,save,digest
from .scan_evidence import canonical,corrections,ordered_rows,SUSPECT

REVISION='failed-scan-source-2'


def bound_to_source(candidate,original):
    """Keep only the pixel text between the source paragraph's first/last words.

    An OCR crop can include a neighbouring paragraph even when every word in
    the crop is recognized correctly. Both paragraph edges must be located in
    the new reading; a missing edge is an inconclusive scan, not permission to
    replace the source with a partial paragraph.
    """
    source_all=re.findall(r'[A-Za-z0-9]+',re.sub(r'<[^>]+>',' ',original))
    source=[word for word in source_all if len(word)>=3 or word.isdigit()]
    found_all=list(re.finditer(r'[A-Za-z0-9]+',candidate))
    found=list(enumerate(found_all))
    if len(source)<2 or len(found)<2:return None
    def match(left,right):
        return difflib.SequenceMatcher(None,left.lower(),right.lower()).ratio()
    def edge(words,reverse=False):
        pairs=[]
        expected=words[-2:] if reverse else words[:2]
        for index in range(len(found)-1):
            for next_index in range(index+1,min(index+4,len(found))):
                actual=[found[index][1][0],found[next_index][1][0]]
                scores=[match(a,b) for a,b in zip(expected,actual)]
                if min(scores)>=.52 and sum(scores)/2>=.58:
                    pairs.append((sum(scores),index,next_index))
        if not pairs:return None
        best=max(score for score,_,_ in pairs)
        options=[(index,next_index) for score,index,next_index in pairs if score>=best-.02]
        return max(options) if reverse else min(options)
    start=edge(source);end=edge(source,True)
    if start is None or end is None or end[1]<start[0]:return None
    first=start[0];last=end[1]
    leading=source_all[:next(i for i,w in enumerate(source_all) if len(w)>=3 or w.isdigit())]
    trailing=source_all[len(source_all)-next(i for i,w in enumerate(reversed(source_all)) if len(w)>=3 or w.isdigit()):]
    for word in reversed(leading):
        if first==0 or found_all[first-1][0].lower()!=word.lower():return None
        first-=1
    for word in trailing:
        if last+1==len(found_all) or found_all[last+1][0].lower()!=word.lower():return None
        last+=1
    stop=found_all[last+1].start() if last+1<len(found_all) else len(candidate)
    return candidate[found_all[first].start():stop].rstrip()


def consensus(first,second,evidence,source=''):
    """Resolve isolated OCR disagreements with independent/source word support."""
    if canonical(first)==canonical(second):return first
    a=list(re.finditer(r'[A-Za-z0-9]+',first));b=list(re.finditer(r'[A-Za-z0-9]+',second))
    supported={canonical(w) for w in re.findall(r'[A-Za-z0-9]+',evidence)}
    source_words={canonical(w) for w in re.findall(r'[A-Za-z0-9]+',source)}
    replacements=[]
    sequence=difflib.SequenceMatcher(None,[canonical(v[0]) for v in a],[canonical(v[0]) for v in b],autojunk=False)
    for tag,i,j,k,l in sequence.get_opcodes():
        if tag=='equal':continue
        if tag=='delete' and i>0 and j<len(a) and j-i<=2:
            if any(canonical(v[0]) in supported or canonical(v[0]) in source_words for v in a[i:j]):return None
            replacements.append((a[i].start(),a[j-1].end(),''));continue
        if tag!='replace' or j-i!=1 or l-k!=1:return None
        left,right=a[i],b[k];x,y=canonical(left[0]),canonical(right[0])
        if (x in supported)!=(y in supported):winner=left[0] if x in supported else right[0]
        elif (x in source_words)!=(y in source_words):winner=left[0] if x in source_words else right[0]
        else:
            previous=canonical(a[i-1][0]) if i else ''
            following=canonical(a[j][0]) if j<len(a) else ''
            image=canonical(evidence);original=canonical(source)
            def anchored(word):
                pairs=[previous+word if previous else '',word+following if following else '']
                return sum(bool(p and image.count(p)==1 and original.count(p)==1) for p in pairs)
            left_score,right_score=anchored(x),anchored(y)
            if left_score==right_score or max(left_score,right_score)==0:return None
            winner=left[0] if left_score>right_score else right[0]
        short_supported=(len(winner)==2 and min(len(x),len(y))==1 and
                         canonical(winner) in supported and canonical(winner) in source_words)
        if max(len(x),len(y))>20 or (difflib.SequenceMatcher(None,x,y).ratio()<.45 and not short_supported):return None
        replacements.append((left.start(),left.end(),winner))
    text=first
    for start,end,value in reversed(replacements):text=text[:start]+value+text[end:]
    return text if replacements else None


class ScanRecovery:
    def __init__(self,folder,failed):
        self.folder=Path(folder);self.failed=set(failed);self.lock=threading.RLock();self.validated=False
        self.state=read(self.folder/'state.json');self.cache=self.folder/'source-recovery';self.cache.mkdir(exist_ok=True)

    def tesseract(self,page,rect,dpi):
        from .ocr import data_path,OCR_SHA
        data=data_path()
        if not self.validated:
            if data is None or digest(data/'eng.traineddata')!=OCR_SHA:raise RuntimeError('원문 복구 OCR 모델 해시 불일치')
            self.validated=True
        pix=page.get_pixmap(matrix=fitz.Matrix(dpi/72,dpi/72),clip=rect,colorspace=fitz.csRGB,alpha=False)
        pix.set_dpi(dpi,dpi)
        with fitz.open('pdf',pix.pdfocr_tobytes(language='eng',tessdata=str(data))) as doc:
            recognized=doc[0];sx=rect.width/recognized.rect.width;sy=rect.height/recognized.rect.height
            rows=[]
            for b in recognized.get_text('dict')['blocks']:
                for line in b.get('lines',[]):
                    for span in line['spans']:
                        a,y,c,d=span['bbox']
                        rows.append(dict(text=span['text'],score=1.,bbox=[rect.x0+a*sx,rect.y0+y*sy,rect.x0+c*sx,rect.y0+d*sy]))
            return ordered_rows(rows)

    def observe(self,item):
        rect=fitz.Rect(item['source_rect']);page_number=item['page']
        # Synthetic OCR glyph boxes can clip the top half of the real letters.
        # Expand only vertically to independently observed rows in this column.
        support=item.get('support_rows',item['rows'])
        for row in support:
            r=fitz.Rect(row['bbox'])
            if r.y0>=rect.y0-12 and r.y1<=rect.y1+12:
                rect.y0=min(rect.y0,r.y0);rect.y1=max(rect.y1,r.y1)
        rect=fitz.Rect(rect.x0-2,rect.y0-2,rect.x1+2,rect.y1+2)
        identity=[REVISION,self.state['source_sha256'],page_number,list(rect)]
        key=hashlib.sha256(json.dumps(identity).encode()).hexdigest();path=self.cache/(key+'.json')
        if path.exists():return read(path)
        with fitz.open(self.folder/'Original.pdf') as original:
            page=original[page_number]
            rect=rect&page.rect
            rows=self.tesseract(page,rect,300);second=self.tesseract(page,rect,400)
        result=dict(revision=REVISION,source_sha256=self.state['source_sha256'],page=page_number,
            rect=list(rect),rows=rows,second_rows=second)
        save(path,result);return result

    def __call__(self,value,paragraph,item):
        source=value.unicode
        if source not in self.failed:return value,[]
        from babeldoc.format.pdf.document_il.midend.il_translator import FormulaPlaceholder
        formulas=[p for p in value.placeholders if isinstance(p,FormulaPlaceholder)]
        if not SUSPECT.search(source) and len(formulas)<5:return value,[]
        with self.lock:observation=self.observe(item)
        changes=[]
        # Two-sided anchors remain mandatory. Do not weaken numeric validation
        # because a language model finds the source's "10" ungrammatical.
        fixed,edits=corrections(source,observation['rows'])
        second,second_edits=corrections(source,observation['second_rows'])
        if fixed==second and edits:
            value.unicode=fixed;changes.extend(dict(action='pixel_confirmed_ocr_confusion',**e) for e in edits)
        embedded=sum(bool(re.search(r'[A-Za-z]'+re.escape(p.placeholder)+r'|'+re.escape(p.placeholder)+r'[A-Za-z]',source)) for p in formulas)
        fragmented=len(formulas)>=5 and embedded>=4 and all(not re.search(r'[=+*/∑∫√α-ω]', ''.join(c.char_unicode or '' for c in p.formula.pdf_character)) for p in formulas)
        if fragmented:
            first=' '.join(r['text'] for r in observation['rows']);second=' '.join(r['text'] for r in observation['second_rows'])
            independent=' '.join(r['text'] for r in ordered_rows(item.get('support_rows',item['rows'])) if r['score']>=.85)
            expanded=source
            for placeholder in formulas:expanded=expanded.replace(placeholder.placeholder,''.join(c.char_unicode or '' for c in placeholder.formula.pdf_character))
            candidate=consensus(first,second,independent,expanded)
            # Independent image OCR must also support the words. Sparse scan
            # evidence can cover only the corrupted band, so compare the
            # first line at its own coordinates, then retain the rest unchanged.
            if candidate is not None and len(canonical(candidate))>=8:
                candidate=bound_to_source(candidate,expanded)
            if candidate is not None and len(canonical(candidate))>=8:
                words=re.findall(r'[A-Za-z]{2,}|\d+',candidate)
                evidence=canonical(independent)
                original_words={w.lower() for w in re.findall(r'[A-Za-z]{2,}|\d+',re.sub('<[^>]+>',' ',expanded))}
                equiv=lambda s:canonical(s).translate(str.maketrans({'i':'l','1':'l','0':'o'}))
                supported=sum(w.lower() in original_words or canonical(w) in evidence or
                    (w.isupper() and len(w)>=3 and equiv(w) in equiv(independent)) for w in words)
                if words and supported/len(words)>=.85:
                    value.unicode=candidate;value.placeholders=[]
                    changes.append(dict(action='pixel_consensus_fragmented_scan_prose',reader_dpis=[300,400],independent_word_support=supported,total_words=len(words)))
        return value,changes
