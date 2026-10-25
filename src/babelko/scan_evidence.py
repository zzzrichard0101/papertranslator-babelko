"""Independent local scan evidence; keep cached input and good translations.

The second reader runs on original pixels, not on a translation. Its results
are content-addressed and retained, so resuming never repeats a finished page.
"""
import copy,difflib,hashlib,re,statistics
from pathlib import Path
import pymupdf as fitz
from .storage import digest,read,save

REVISION='scan-evidence-2'
LAYOUT_REVISION='scan-band-layout-4'
MODEL_HASHES={
    'ch_PP-OCRv4_det_infer.onnx':'d2a7720d45a54257208b1e13e36a8479894cb74155a5efe29462512d42f49da9',
    'ch_PP-OCRv4_rec_infer.onnx':'48fc40f24f6d2a207a2b1091d3437eb3cc3eb6b676dc3ef9c37384005483683b',
    'ch_ppocr_mobile_v2.0_cls_infer.onnx':'e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c',
}
STYLE=re.compile(r"<style\s+id=['\"]\d+['\"]>|</style>")
SUSPECT=re.compile(r'(?<![A-Za-z0-9])(?:1am|1f|1s|10|0|1)(?![A-Za-z0-9])',re.I)
ALTERNATIVES={'1am':['I am'],'1f':['If'],'1s':['is'],'10':['to'],'0':['to'],'1':['I']}


def canonical(text):return re.sub(r'[^a-z0-9]','',text.lower())


def ordered_rows(rows):
    """Reading order by shared baselines, not independently rounded top edges."""
    if not rows or any('bbox' not in r for r in rows):return list(rows)
    lines=[]
    for row in sorted(rows,key=lambda r:((r['bbox'][1]+r['bbox'][3])/2,r['bbox'][0])):
        a,b,c,d=row['bbox'];center=(b+d)/2;height=d-b
        candidates=[line for line in lines if abs(center-line[0])<=max(2,min(height,line[1])*.55)]
        if candidates:
            line=min(candidates,key=lambda line:abs(center-line[0]));line[2].append(row)
        else:lines.append([center,height,[row]])
    return [r for line in lines for r in sorted(line[2],key=lambda r:r['bbox'][0])]


def running_scan_headers(paragraphs,page_height):
    """Keep numbered book headers in the original raster, not translation IL.

    A scan can produce two overlapping, contradictory OCR interpretations of
    the same printed header. A leading page number in the upper margin anchors
    the header; only co-located title fragments with that same number join it.
    """
    top=[p for p in paragraphs if getattr(p,'box',None) is not None and
         getattr(p,'layout_label','')=='title' and p.box.y>page_height-110]
    anchors=[]
    for p in top:
        match=re.match(r'^\s*(\d{1,3})\s+[A-Za-z]',getattr(p,'unicode','') or '')
        if match:anchors.append((p,match[1]))
    chosen={id(p) for p,_ in anchors}
    for paragraph in top:
        if id(paragraph) in chosen:continue
        value=getattr(paragraph,'unicode','') or ''
        for anchor,number in anchors:
            if re.search(r'(?<!\d)'+re.escape(number)+r'(?!\d)',value) and min(paragraph.box.y2,anchor.box.y2)>=max(paragraph.box.y,anchor.box.y)-5:
                chosen.add(id(paragraph));break
    return chosen


def corrections(source,rows):
    """Replace only a digit/letter confusion with exact, two-sided evidence.

    A plausible grammar guess is insufficient. Both surrounding anchors AND
    the replacement must occur together in independent high-confidence OCR.
    Real numeric quantities remain subject to the original strict validator.
    """
    visible=STYLE.sub(lambda m:' '*len(m[0]),source)
    evidence=canonical(' '.join(r['text'] for r in ordered_rows(rows) if r['score']>=.94))
    edits=[]
    for match in SUSPECT.finditer(visible):
        left=canonical(re.sub(r'\{v\d+\}',' ',visible[:match.start()]))[-12:]
        right=canonical(re.sub(r'\{v\d+\}',' ',visible[match.end():]))[:12]
        if min(len(left),len(right))<8:continue
        choices=[v for v in ALTERNATIVES[match[0].lower()] if evidence.count(left+canonical(v)+right)==1]
        if len(choices)==1:edits.append(dict(start=match.start(),end=match.end(),before=match[0],after=choices[0],left=left,right=right))
    result=source
    for edit in reversed(edits):result=result[:edit['start']]+edit['after']+result[edit['end']:]
    return result,edits


def normalize_input(value,item):
    from babeldoc.format.pdf.document_il.midend.il_translator import FormulaPlaceholder,RichTextPlaceholder
    source=value.unicode
    changed,edits=corrections(source,item['rows'])
    value.unicode=changed
    letters=[p for p in value.placeholders if isinstance(p,FormulaPlaceholder) and
             re.fullmatch(r'[A-Za-z]{1,3}',''.join(c.char_unicode or '' for c in p.formula.pdf_character))]
    # OCR may classify pieces of an ordinary word as dozens of equations.
    # Expand only after the whole prose is independently present in the image.
    if len(letters)>=4:
        expanded=value.unicode
        for p in letters:expanded=expanded.replace(p.placeholder,''.join(c.char_unicode or '' for c in p.formula.pdf_character))
        needle=canonical(STYLE.sub('',expanded))
        haystack=canonical(' '.join(r['text'] for r in item['rows'] if r['score']>=.94))
        if len(needle)>=20 and needle in haystack and not re.search(r'\{v\d+\}',expanded):
            value.unicode=expanded
            value.placeholders=[p for p in value.placeholders if p not in letters]
            edits.append(dict(action='expose_image_confirmed_prose',count=len(letters)))
    if any(failed in source for failed in item.get('failed_styles',[])):
        value.unicode=STYLE.sub(' ',value.unicode)
        value.placeholders=[p for p in value.placeholders if not isinstance(p,RichTextPlaceholder)]
        edits.append(dict(action='flatten_failed_synthetic_scan_styles'))
    return source,value.unicode,edits


class Reader:
    def __init__(self):self.engine=None
    def recognize(self,page,clip=None):
        import numpy as np,cv2,onnxruntime,rapidocr_onnxruntime
        from rapidocr_onnxruntime import RapidOCR
        if self.engine is None:
            model_dir=Path(rapidocr_onnxruntime.__file__).parent/'models'
            for name,sha in MODEL_HASHES.items():
                if digest(model_dir/name)!=sha:raise RuntimeError('보완 OCR 모델 해시 불일치')
            onnxruntime.disable_telemetry_events();cv2.setNumThreads(4)
            self.engine=RapidOCR(intra_op_num_threads=4,inter_op_num_threads=1,det_limit_side_len=2048,
                max_side_len=3500,text_score=0.,det_use_cuda=False,rec_use_cuda=False,cls_use_cuda=False,
                det_use_dml=False,rec_use_dml=False,cls_use_dml=False)
        scale=min(220/72,3500/max(page.rect.width,page.rect.height))
        clip=fitz.Rect(clip or page.rect)&page.rect
        pix=page.get_pixmap(matrix=fitz.Matrix(scale,scale),clip=clip,colorspace=fitz.csRGB,alpha=False)
        pixels=np.frombuffer(pix.samples,np.uint8).reshape(pix.height,pix.width,3)
        result,_=self.engine(pixels[:,:,::-1].copy())
        sx=clip.width/pix.width;sy=clip.height/pix.height
        rows=[]
        for points,text,score in result or []:
            if not text.strip():continue
            box=[clip.x0+min(p[0] for p in points)*sx,clip.y0+min(p[1] for p in points)*sy,clip.x0+max(p[0] for p in points)*sx,clip.y0+max(p[1] for p in points)*sy]
            rows.append(dict(text=text,score=float(score),bbox=box))
        return sorted(rows,key=lambda r:(round(r['bbox'][1]/3),r['bbox'][0]))


def suspect_regions(page):
    """Inspect existing OCR, then reread only risky rows, not every book page."""
    spans=[s for b in page.get_text('dict')['blocks'] for line in b.get('lines',[]) for s in line['spans'] if s['text'].strip()]
    # This function is reached only for pages selected for OCR. A raster page
    # with *zero* extracted spans is the most important failure to audit:
    # span-based risk rules have no anchor and would otherwise skip it entirely.
    if not spans:return [page.rect] if page.get_image_info() else []
    median=statistics.median(s['size'] for s in spans)
    regions=[]
    for s in spans:
        suspect=(s['size']>max(24,median*1.8) or
                 (len(s['text'])>30 and SUSPECT.search(s['text'])))
        if not suspect:continue
        r=fitz.Rect(s['bbox']);r=fitz.Rect(0,max(0,r.y0-20),page.rect.width,min(page.rect.height,r.y1+20))
        regions.append(r)
    merged=[]
    for r in sorted(regions,key=lambda r:r.y0):
        if merged and r.y0<=merged[-1].y1+4:merged[-1]|=r
        else:merged.append(r)
    if sum(r.get_area() for r in merged)>page.rect.get_area()*.65:return [page.rect]
    return merged


def damaged_bands(page):
    spans=[s for b in page.get_text('dict')['blocks'] for line in b.get('lines',[]) for s in line['spans'] if s['text'].strip()]
    if not spans:return []
    median=statistics.median(s['size'] for s in spans);bands=[]
    for s in spans:
        if s['size']<=max(28,median*2.5):continue
        box=fitz.Rect(s['bbox']);r=fitz.Rect(0,max(0,box.y0-20),page.rect.width,min(page.rect.height,box.y1+20))
        bands.append(r)
    merged=[]
    for r in sorted(bands,key=lambda b:b.y0):
        if merged and r.y0<=merged[-1].y1+4:merged[-1]|=r
        else:merged.append(r)
    return merged


def reconstruct_band(page,original,region,rows):
    """Replace a damaged OCR band, preserving pixels outside it and all scans.

    No horizontal glyph morph: its geometric-mean size was being interpreted
    as an actual font size by the downstream PDF parser.
    """
    import cv2,numpy as np
    scale=3;pix=original.get_pixmap(matrix=fitz.Matrix(scale,scale),clip=region,colorspace=fitz.csRGB,alpha=False)
    pixels=np.frombuffer(pix.samples,np.uint8).reshape(pix.height,pix.width,3).copy();original_pixels=pixels.copy()
    spans=[s for b in page.get_text('dict')['blocks'] for line in b.get('lines',[]) for s in line['spans'] if s['text'].strip()]
    body_size=statistics.median(s['size'] for s in spans) if spans else 12
    chosen=[]
    for row in rows:
        r=fitz.Rect(row['bbox']);baseline=fitz.Point((r.x0+r.x1)/2,r.y0+r.height*.78)
        agreement=any(canonical(s['text'])==canonical(row['text']) for s in spans)
        if (r&region).is_empty or (row['score']<.94 and not (row['score']>=.8 and agreement)):continue
        # Keep math as original image, not guessed plain text.
        if re.search(r'[∑∫∂√≤≥=]',row['text']):continue
        if baseline in region:
            # Restore word spaces when the first reader agrees on every
            # letter; detector/recognizer output sometimes joins whole titles.
            same=next((s['text'] for s in spans if canonical(s['text'])==canonical(row['text'])),None)
            chosen.append({**row,'text':same or row['text']})
        x0=max(0,int((r.x0-region.x0)*pix.width/region.width));x1=min(pix.width,int((r.x1-region.x0)*pix.width/region.width)+1)
        y0=max(0,int((r.y0-region.y0)*pix.height/region.height));y1=min(pix.height,int((r.y1-region.y0)*pix.height/region.height)+1)
        pixels[y0:y1,x0:x1]=255
    # Keep all old prose unless the independent rows cover its content. In
    # particular a low-confidence table row cannot silently disappear.
    stream_items=[]
    for xref in page.get_contents():
        stream=page.parent.xref_stream(xref)
        if not re.search(rb'\bBT\b',stream):continue
        matrices=re.findall(rb'1 0 0 1 ([-.\d]+) ([-.\d]+) Tm',stream)
        if len(matrices)!=1 or len(re.findall(rb'\bBT\b',stream))!=1 or b'/helv ' not in stream:
            raise ValueError('복구 대상 OCR 내용 형식 불일치: 원본 입력을 보존했습니다.')
        x,y=map(float,matrices[0]);baseline_y=page.rect.height-y
        if not region.y0<=baseline_y<=region.y1:continue
        parts=[s for s in spans if abs(s['origin'][1]-baseline_y)<.1 and abs(s['origin'][0]-x)<.25]
        text=' '.join(s['text'] for s in parts)
        words=re.findall(r'[A-Za-z]{2,}|\d+',text)
        large_short=bool(parts) and max(s['size'] for s in parts)>body_size*2.5 and len(canonical(text))<=3
        if parts:
            from types import SimpleNamespace
            box=fitz.Rect(parts[0]['bbox'])
            meaningful=[r for r in rows if r['score']>=.94 and not (fitz.Rect(r['bbox'])&box).is_empty]
            present=any(re.search(r'\b'+re.escape(text.strip())+r'\b',r['text'],re.I) for r in meaningful) if text.strip() else False
            if not present and rule_only(original,SimpleNamespace(x=box.x0,x2=box.x1,y=original.rect.height-box.y1,y2=original.rect.height-box.y0),meaningful):large_short=True
        stream_items.append((xref,parts,baseline_y,words,large_short))
    # Do not insert a second rendition across a retained source row. That row
    # keeps its original text object and remains visible to native translation.
    def overlaps_legacy(row):
        r=fitz.Rect(row['bbox']);baseline=r.y0+r.height*.78
        return any(abs(s['origin'][1]-baseline)<=r.height*.5 and
                   max(0,min(s['bbox'][2],r.x1)-max(s['bbox'][0],r.x0))>min(r.width,s['bbox'][2]-s['bbox'][0])*.4 for s in retained)
    # A retained fragment may block a replacement row. Recompute removals to a
    # fixed point so a neighboring run is NEVER deleted without its replacement.
    while True:
        removed=[];retained=[]
        for xref,parts,baseline_y,words,large_short in stream_items:
            nearby=[r for r in chosen if abs(r['bbox'][1]+(r['bbox'][3]-r['bbox'][1])*.78-baseline_y)<=max(4,(r['bbox'][3]-r['bbox'][1])*.5)]
            alternative=canonical(' '.join(r['text'] for r in sorted(nearby,key=lambda r:r['bbox'][0])))
            covered=bool(nearby) and bool(words) and all(alternative.count(canonical(w))>=words.count(w) for w in words)
            if covered or large_short:removed.append(xref)
            else:retained.extend(parts)
        remaining=[r for r in chosen if not overlaps_legacy(r)]
        if len(remaining)==len(chosen):break
        chosen=remaining
    normalized_runs=[]
    for xref,parts,baseline_y,words,large_short in stream_items:
        if xref in removed or len(parts)!=1:continue
        s=parts[0];token=canonical(s['text'])
        if s['size']<=body_size*1.6 or len(token)<4:continue
        matches=[r for r in rows if r['score']>=.8 and token in canonical(r['text']) and
                 abs(r['bbox'][1]+(r['bbox'][3]-r['bbox'][1])*.78-baseline_y)<(r['bbox'][3]-r['bbox'][1])*.7 and
                 r['bbox'][0]-3<=s['origin'][0]<=r['bbox'][2]]
        if len(matches)!=1:continue
        r=matches[0];height=r['bbox'][3]-r['bbox'][1]
        size=min(s['size'],height*.72)
        if size>=s['size']*.85:continue
        normalized_runs.append(dict(text=s['text'],origin=(s['origin'][0],r['bbox'][1]+height*.78),size=size))
        removed.append(xref)
    # Erase recognized legacy ink in the raster copy as well; its preserved PDF
    # text object is painted ABOVE this new background until translation.
    for s in spans:
        if s['size']>body_size*2.5 and s not in retained:continue
        r=fitz.Rect(s['bbox'])&region
        if r.is_empty:continue
        x0=max(0,int((r.x0-region.x0)*pix.width/region.width));x1=min(pix.width,int((r.x1-region.x0)*pix.width/region.width)+1)
        y0=max(0,int((r.y0-region.y0)*pix.height/region.height));y1=min(pix.height,int((r.y1-region.y0)*pix.height/region.height)+1)
        pixels[y0:y1,x0:x1]=255
    # Long table rules are graphics, not removable text ink.
    gray=cv2.cvtColor(original_pixels,cv2.COLOR_RGB2GRAY);ink=cv2.threshold(gray,150,255,cv2.THRESH_BINARY_INV)[1]
    rules=cv2.morphologyEx(ink,cv2.MORPH_OPEN,np.ones((1,max(80,pix.width//8)),np.uint8))
    mask=cv2.dilate(rules,np.ones((3,3),np.uint8))>0;pixels[mask]=original_pixels[mask]
    # Redaction deletes any character whose oversized bbox merely touches a
    # band, including neighboring lines. Our generated OCR input has one
    # Helvetica text object per stream: remove whole runs by their baseline.
    # Fail closed on a different content grammar rather than deleting prose.
    for xref in removed:page.parent.update_stream(xref,b'')
    clean=fitz.Pixmap(fitz.csRGB,pix.width,pix.height,pixels.tobytes(),False)
    page.insert_image(region,pixmap=clean)
    contents=page.get_contents();image_stream=contents.pop()
    first_text=next((i for i,x in enumerate(contents) if re.search(rb'\bBT\b',page.parent.xref_stream(x))),len(contents))
    contents.insert(first_text,image_stream)
    page.parent.xref_set_key(page.xref,'Contents','['+' '.join(f'{x} 0 R' for x in contents)+']')
    font=fitz.Font('helv')
    for row in chosen:
        r=fitz.Rect(row['bbox']);text=row['text']
        # A word's natural advance and its measured row height independently
        # cap the em size; no stretch-induced type-size inflation.
        size=min(r.height*.72,r.width/max(.1,font.text_length(text,fontsize=1)))
        if size<=0:continue
        page.insert_text((r.x0,r.y0+r.height*.78),text,fontname='helv',fontsize=size)
    for run in normalized_runs:page.insert_text(run['origin'],run['text'],fontname='helv',fontsize=run['size'])
    return len(chosen)


def layout_input(folder,rows,progress=lambda *_:None,cancel=lambda:False):
    """A derived layout input. Original.pdf and Input.pdf remain byte-identical."""
    state=read(folder/'state.json');manifest=folder/'layout-input.json';output=folder/'Layout-input.pdf'
    signature=hashlib.sha256(str([LAYOUT_REVISION,state['input_sha256'],sorted((i,hashlib.sha256(str(r).encode()).hexdigest()) for i,r in rows.items())]).encode()).hexdigest()
    old=read(manifest) if manifest.is_file() else {}
    if old.get('signature')==signature and output.is_file() and digest(output)==old.get('sha256'):return output
    changes=[]
    with fitz.open(folder/'Input.pdf') as doc,fitz.open(folder/'Original.pdf') as original:
        for index,recognized in sorted(rows.items()):
            if cancel():raise InterruptedError('취소됨')
            regions=damaged_bands(doc[index])
            if not regions:continue
            progress(f'OCR 조판 복구 · 원문 {index+1}쪽 · 번역 체크포인트 유지')
            for region in regions:
                changes.append(dict(page=index+1,bbox=list(region),rows=reconstruct_band(doc[index],original[index],region,recognized)))
        if not changes:return folder/'Input.pdf'
        pending=folder/'Layout-input.pending.pdf'
        doc.save(pending,garbage=4,deflate=True)
    if cancel():raise InterruptedError('취소됨')
    sha=digest(pending);pending.replace(output)
    save(manifest,dict(revision=LAYOUT_REVISION,signature=signature,sha256=sha,original_input_sha256=state['input_sha256'],bands=changes))
    return output


def recognition_workers(count):
    # Local 8- and 32-page controls were slower with two CPU readers. Keep the
    # measured serial default; explicit workers is for controlled benchmarking.
    return 1


_region_reader=None
_region_doc=None
_region_source=None


def recognize_task(task):
    """Spawn-safe CPU task; all writes and ordered commits stay in the parent."""
    global _region_reader,_region_doc,_region_source
    source,index,regions,cancel_path=task
    if Path(cancel_path).exists():raise InterruptedError('취소됨')
    if _region_reader is None:_region_reader=Reader()
    if _region_source!=source:
        if _region_doc is not None:_region_doc.close()
        _region_doc=fitz.open(source);_region_source=source
    rows=[]
    for region in regions:
        if Path(cancel_path).exists():raise InterruptedError('취소됨')
        rows.extend(_region_reader.recognize(_region_doc[index],region))
    return rows


def evidence(folder,selected,progress=lambda *_:None,cancel=lambda:False,workers=None):
    state=read(folder/'state.json');pages=sorted(set(selected)&set(state.get('ocr_pages',[])))
    cache=folder/'scan-evidence';cache.mkdir(exist_ok=True);reader=Reader();result={}
    pending=[]
    with fitz.open(folder/'Input.pdf') as input_doc:
        for n,index in enumerate(pages):
            if cancel():raise InterruptedError('취소됨')
            signature=hashlib.sha256(str([REVISION,state['source_sha256'],index,MODEL_HASHES]).encode()).hexdigest()
            path=cache/f'page-{index+1}.json';row=read(path) if path.is_file() else {}
            if row.get('signature')!=signature or (row.get('scope')=='regions' and row.get('input_sha256')!=state.get('input_sha256')):
                regions=suspect_regions(input_doc[index])
                row=dict(signature=signature,revision=REVISION,page=index+1,scope='regions',input_sha256=state.get('input_sha256'),regions=[list(r) for r in regions])
                if regions:pending.append((index,path,row));continue
                row['rows']=[];save(path,row)
            result[index]=row['rows']
    count=min(2,max(1,workers if workers is not None else recognition_workers(len(pending))))
    def commit(item,recognized,n):
        index,path,row=item;row['rows']=recognized;save(path,row);result[index]=recognized
        progress(f'스캔 원문 보완 인식 {n+1}/{len(pending)} · CPU {count}개 · 저장된 번역 유지')
    if count>1:
        import multiprocessing
        from concurrent.futures import ProcessPoolExecutor
        tasks=[(str(folder/'Original.pdf'),index,row['regions'],str(folder/'cancel')) for index,_,row in pending]
        pool=ProcessPoolExecutor(max_workers=count,mp_context=multiprocessing.get_context('spawn'))
        try:
            for n,(item,recognized) in enumerate(zip(pending,pool.map(recognize_task,tasks))):
                if cancel():raise InterruptedError('취소됨')
                commit(item,recognized,n)
        finally:pool.shutdown(wait=True,cancel_futures=True)
    elif pending:
        with fitz.open(folder/'Original.pdf') as doc:
            for n,item in enumerate(pending):
                index,_,row=item;recognized=[]
                for region in row['regions']:
                    if cancel():raise InterruptedError('취소됨')
                    recognized.extend(reader.recognize(doc[index],region))
                commit(item,recognized,n)
    return result


def matching_rows(box,height,rows):
    rect=fitz.Rect(box.x,height-box.y2,box.x2,height-box.y)
    found=[]
    for row in rows:
        if row['score']<.94:continue
        r=fitz.Rect(row['bbox']);intersection=rect&r
        if intersection.is_empty:continue
        if intersection.width>=r.width*.65 and intersection.height>=r.height*.55:found.append(row)
    return found


def rule_only(page,box,known_rows=()):
    """Positive pixel evidence, not a language-model guess about gibberish."""
    import numpy as np,cv2
    rect=fitz.Rect(box.x,page.rect.height-box.y2,box.x2,page.rect.height-box.y)&page.rect
    if rect.is_empty or rect.width<8:return False
    pix=page.get_pixmap(matrix=fitz.Matrix(3,3),clip=rect,colorspace=fitz.csGRAY,alpha=False)
    pixels=np.frombuffer(pix.samples,np.uint8).reshape(pix.height,pix.width)
    ink=cv2.threshold(pixels,150,255,cv2.THRESH_BINARY_INV)[1]
    # An oversized false glyph box may also overlap a genuine heading. Remove
    # the independently recognized text from this classifier only, so a rule
    # underneath the heading is not mistaken for more letters.
    for row in known_rows:
        r=fitz.Rect(row['bbox'])&rect
        if r.is_empty:continue
        x0=max(0,int((r.x0-rect.x0)*pix.width/rect.width));x1=min(pix.width,int((r.x1-rect.x0)*pix.width/rect.width)+1)
        y0=max(0,int((r.y0-rect.y0)*pix.height/rect.height));y1=min(pix.height,int((r.y1-rect.y0)*pix.height/rect.height)+1)
        ink[y0:y1,x0:x1]=0
    total=int(np.count_nonzero(ink))
    if total<10:return False
    rules=cv2.morphologyEx(ink,cv2.MORPH_OPEN,np.ones((1,max(8,min(60,int(pix.width*.5)))),np.uint8))
    # Allow a slightly sloped scan rule; dilation is constrained to actual ink.
    covered=(cv2.dilate(rules,np.ones((5,3),np.uint8))>0)&(ink>0)
    return int(np.count_nonzero(covered))/total>=.92


def raster_single_glyph(page,box,source,known_rows=()):
    """Find a single printed figure/section glyph plus a long raster rule.

    A bad scan text layer can turn one large letter or table symbol into many
    fake words. The real glyph remains in the original raster, so dropping
    that OCR paragraph preserves its appearance and avoids translating noise.
    Reject ordinary headings, lines of prose, and a bare rule.
    """
    visible=STYLE.sub('',source or '')
    if len(visible)>100 or len(re.findall(r'[A-Za-z]+',visible))<2:return False
    rect=fitz.Rect(box.x,page.rect.height-box.y2,box.x2,page.rect.height-box.y)&page.rect
    if rect.width<20 or rect.height>55 or rect.is_empty:return False
    import cv2,numpy as np
    pix=page.get_pixmap(matrix=fitz.Matrix(3,3),clip=rect,colorspace=fitz.csGRAY,alpha=False)
    gray=np.frombuffer(pix.samples,np.uint8).reshape(pix.height,pix.width)
    kernel=max(12,int(pix.width*.08))
    for threshold in (100,150):
        ink=cv2.threshold(gray,threshold,255,cv2.THRESH_BINARY_INV)[1]
        rules=cv2.morphologyEx(ink,cv2.MORPH_OPEN,np.ones((1,kernel),np.uint8))
        if np.count_nonzero(np.any(rules>0,axis=0))<pix.width*.6:continue
        mask=cv2.dilate(rules,np.ones((5,3),np.uint8))>0
        remaining=ink.copy();remaining[mask]=0
        count,_,stats,_=cv2.connectedComponentsWithStats(remaining)
        minimum=max(8,int(pix.width*pix.height*.00005))
        glyphs=[s for s in stats[1:count] if s[cv2.CC_STAT_AREA]>=minimum and
            s[cv2.CC_STAT_WIDTH]>=2 and s[cv2.CC_STAT_HEIGHT]>=2 and
            s[cv2.CC_STAT_TOP]+s[cv2.CC_STAT_HEIGHT]<pix.height*.88]
        if 1<=len(glyphs)<=3:
            left=min(s[cv2.CC_STAT_LEFT] for s in glyphs)
            right=max(s[cv2.CC_STAT_LEFT]+s[cv2.CC_STAT_WIDTH] for s in glyphs)
            center=(left+right)/2
            if right-left<=pix.width*.25 and abs(center-pix.width/2)<=pix.width*.25:return True
        observed=[r for r in known_rows if r['score']>=.82 and not (fitz.Rect(r['bbox'])&rect).is_empty and
            (fitz.Rect(r['bbox'])&rect).get_area()>=fitz.Rect(r['bbox']).get_area()*.6]
        if len(observed)==1 and re.fullmatch(r'[A-Z0-9]',observed[0]['text'].strip()):return True
    return False


def duplicate_title(paragraph,peers):
    """Discard only a shorter OCR layer covering the same printed title."""
    if getattr(paragraph,'layout_label','')!='title' or not paragraph.box:return False
    short=canonical(STYLE.sub('',paragraph.unicode or ''))
    if len(short)<12:return False
    a=paragraph.box;area=(a.x2-a.x)*(a.y2-a.y)
    if area<=0:return False
    for peer in peers:
        if peer is paragraph or getattr(peer,'layout_label','')!='title' or not peer.box:continue
        long=canonical(STYLE.sub('',peer.unicode or ''))
        if len(long)<len(short)+5:continue
        similar=short in long or any(difflib.SequenceMatcher(None,short,long[i:i+len(short)]).ratio()>=.9
            for i in range(len(long)-len(short)+1))
        if not similar:continue
        b=peer.box;overlap=max(0,min(a.x2,b.x2)-max(a.x,b.x))*max(0,min(a.y2,b.y2)-max(a.y,b.y))
        if overlap/area>=.75:return True
    return False


def cached(folder):
    """Read only verified cache entries, without starting a second reader."""
    state=read(folder/'state.json');result={}
    for path in (folder/'scan-evidence').glob('page-*.json'):
        row=read(path);index=row['page']-1
        expected=hashlib.sha256(str([REVISION,state['source_sha256'],index,MODEL_HASHES]).encode()).hexdigest()
        if row.get('signature')==expected and (row.get('scope')!='regions' or row.get('input_sha256')==state.get('input_sha256')):result[index]=row['rows']
    return result


def plan(docs,folder,rows,report_folder=None):
    """Compute from source geometry; change output typography only after replay."""
    if not rows:return {}
    plans={};report=[]
    with fitz.open(folder/'Original.pdf') as original:
        for page in docs.page:
            index=page.page_number
            if index not in rows:continue
            src=original[index];kept=[]
            headers=running_scan_headers(page.pdf_paragraph,src.rect.height)
            for p in page.pdf_paragraph:
                if not p.box:kept.append(p);continue
                if id(p) in headers:
                    report.append(dict(page=index+1,id=p.debug_id,action='preserve_raster_running_header',source=p.unicode));continue
                if duplicate_title(p,page.pdf_paragraph):
                    report.append(dict(page=index+1,id=p.debug_id,action='exclude_duplicate_scan_title',source=p.unicode));continue
                found=matching_rows(p.box,src.rect.height,rows[index])
                # Never discard equations, image labels or body text on a weak
                # OCR confidence score. Only isolated physical rules qualify.
                is_rule=not found and p.layout_label in {'text','plain text','title','fallback_line','abandon'} and rule_only(src,p.box)
                if is_rule:
                    report.append(dict(page=index+1,id=p.debug_id,action='exclude_rule',source=p.unicode));continue
                if raster_single_glyph(src,p.box,p.unicode,rows[index]):
                    report.append(dict(page=index+1,id=p.debug_id,action='preserve_raster_single_glyph',source=p.unicode));continue
                kept.append(p)
                size=statistics.median(r['bbox'][3]-r['bbox'][1] for r in found)*.72 if found else None
                # Preserve formulas and intentional typography in native PDFs.
                # Scans have synthetic Helvetica, not recoverable rich styles.
                plans[(index,p.debug_id)]=dict(size=round(size,2) if size and 5<=size<=60 else None,
                    rows=found,page=index,source_rect=[p.box.x,src.rect.height-p.box.y2,p.box.x2,src.rect.height-p.box.y],
                    support_rows=[r for r in rows[index] if r['score']>=.85 and
                        max(0,min(p.box.x2,r['bbox'][2])-max(p.box.x,r['bbox'][0]))>=(r['bbox'][2]-r['bbox'][0])*.65 and
                        max(0,min(src.rect.height-p.box.y,r['bbox'][3])-max(src.rect.height-p.box.y2,r['bbox'][1]))>=(r['bbox'][3]-r['bbox'][1])*.15])
                if size and 5<=size<=60:
                    report.append(dict(page=index+1,id=p.debug_id,action='scan_typography',size=round(size,2),source=p.unicode))
            page.pdf_paragraph=kept
    save((report_folder or folder)/'scan-layout-repairs.json',dict(revision=REVISION,paragraphs=report))
    return plans


def apply(docs,plans):
    if not plans:return
    for page in docs.page:
        for p in page.pdf_paragraph:
            item=plans.get((page.page_number,p.debug_id))
            if not item or item.get('size') is None:continue
            # Only translated Unicode runs: original glyphs/formulas retain
            # exact metrics. Do not mutate shared style objects used elsewhere.
            for comp in p.pdf_paragraph_composition:
                run=comp.pdf_same_style_unicode_characters
                if run and run.pdf_style:
                    run.pdf_style=copy.copy(run.pdf_style);run.pdf_style.font_size=min(run.pdf_style.font_size,item['size'])
            if p.pdf_style:p.pdf_style=copy.copy(p.pdf_style);p.pdf_style.font_size=min(p.pdf_style.font_size,item['size'])
