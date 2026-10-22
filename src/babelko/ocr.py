"""Local searchable input for scans; original PDF remains separate."""
import math,os,shutil,re,hashlib,json,uuid
from pathlib import Path
import pymupdf as fitz
from .storage import digest,save,read
OCR_SHA='8280aed0782fe27257a68ea10fe7ef324ca0f8d85bd2fd145d1c2b560bcb66ba'


def needs_ocr(page,mode):
    if mode=='off':return False
    if mode=='force':return True
    text=page.get_text()
    # Union, rather than sum: repeated/overlapping images must not make a
    # small illustration look like a full-page scan.
    boxes=[fitz.Rect(x['bbox']) & page.rect for x in page.get_image_info()]
    xs=sorted({x for b in boxes if not b.is_empty for x in (b.x0,b.x1)})
    area=0
    for left,right in zip(xs,xs[1:]):
        intervals=sorted((b.y0,b.y1) for b in boxes if b.x0<right and b.x1>left)
        height=0;end=-math.inf
        for lo,hi in intervals:
            height+=max(0,hi-max(lo,end));end=max(end,hi)
        area+=(right-left)*height
    if area<=page.rect.get_area()*.6:return False
    compact=re.sub(r'\s','',text)
    fragmented=sum(len(re.sub(r'\s','',m[0])) for m in re.finditer(r'(?:\b[A-Za-z]\s+){4,}[A-Za-z]\b',text))
    return len(text.strip())<100 or (len(compact)>80 and fragmented/len(compact)>.12) or compact.count('\ufffd')>max(3,len(compact)*.02)


def data_path():
    from .storage import root
    candidates=[root()/'assets/ocr',Path(os.environ['LOCALAPPDATA'])/'PaperTranslator/app-v0.5.10a1/_internal/papertranslator/ocr_models']
    return next((p for p in candidates if (p/'eng.traineddata').is_file()),None)


def prepare(source,destination,mode='auto',progress=print,cancel=lambda:False,selected=None,report_path=None):
    if mode not in {'auto','off','force'}:raise ValueError('OCR 설정 오류')
    # Leave native PDFs byte-for-byte intact: page-by-page grafting discards
    # outlines and transparency groups and repeats shared font resources.
    with fitz.open(source) as doc:
        needed=[];rotated=[]
        for i,page in enumerate(doc):
            if cancel():raise InterruptedError('취소됨')
            if selected is not None and i not in selected:continue
            if page.rotation:rotated.append(i)
            if needs_ocr(page,mode):needed.append(i)
    report_path=Path(report_path) if report_path else Path(destination).with_suffix('.transformations.json')
    if not needed and not rotated:
        shutil.copyfile(source,destination);save(report_path,dict(pages=[]));return []
    done=[];transforms=[];result=fitz.open();validated_data=None
    cache=Path(destination).parent/'primary-ocr-pages';cache.mkdir(exist_ok=True)
    source_sha=digest(source) if needed else None;implementation=digest(Path(__file__))
    cache_hits=0
    with fitz.open(source) as doc:
        for i,page in enumerate(doc):
            if cancel():raise InterruptedError('취소됨')
            if i in needed:
                signature=hashlib.sha256(json.dumps([source_sha,implementation,OCR_SHA,i,list(page.rect),page.rotation]).encode()).hexdigest()
                cached=cache/f'page-{i+1}.pdf';manifest=cached.with_suffix('.json')
                row=read(manifest) if manifest.is_file() else {}
                if row.get('signature')==signature and cached.is_file() and digest(cached)==row.get('sha256'):
                    with fitz.open(cached) as recognized:result.insert_pdf(recognized)
                    cache_hits+=1;done.append(i);progress(f'저장된 로컬 OCR 재사용 {i+1}/{len(doc)}');continue
                if validated_data is None:
                    validated_data=data_path()
                    if not validated_data or digest(validated_data/'eng.traineddata')!=OCR_SHA:raise RuntimeError('검증된 영어 OCR 데이터가 필요합니다. 설정 준비를 다시 실행하세요.')
                data=validated_data
                progress(f'로컬 OCR {i+1}/{len(doc)}')
                scale=min(220/72,3500/max(page.rect.width,page.rect.height),math.sqrt(12000000/page.rect.get_area()))
                pix=page.get_pixmap(matrix=fitz.Matrix(scale,scale),colorspace=fitz.csRGB,alpha=False)
                pix.set_dpi(round(72*scale),round(72*scale))
                raw=pix.pdfocr_tobytes(language='eng',tessdata=str(data))
                with fitz.open('pdf',raw) as recognized:
                    # pdfocr uses rounded DPI; normalize physical geometry.
                    normalized=result.new_page(width=page.rect.width,height=page.rect.height)
                    import numpy as np
                    pixels=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width,3).copy()
                    spans=[s for block in recognized[0].get_text('dict')['blocks'] for line in block.get('lines',[]) for s in line['spans'] if s['text'].strip()]
                    rx=pix.width/recognized[0].rect.width;ry=pix.height/recognized[0].rect.height
                    for span in spans:
                        x0,y0,x1,y1=span['bbox']
                        pixels[max(0,int(y0*ry)-2):min(pix.height,math.ceil(y1*ry)+2),max(0,int(x0*rx)-2):min(pix.width,math.ceil(x1*rx)+2)]=255
                    clean=fitz.Pixmap(fitz.csRGB,pix.width,pix.height,pixels.tobytes(),False)
                    normalized.insert_image(normalized.rect,pixmap=clean)
                    # Reconstruct actual glyphs at OCR positions. The original ink
                    # was removed from this input copy, so normal PDF typesetting
                    # removes English without scan-mask ghosts or glyphless numbers.
                    font=fitz.Font('helv');sx=page.rect.width/recognized[0].rect.width;sy=page.rect.height/recognized[0].rect.height
                    import statistics
                    lines=[line for block in recognized[0].get_text('dict')['blocks'] for line in block.get('lines',[])]
                    runs=[]
                    for line in lines:
                        items=sorted([s for s in line['spans'] if s['text'].strip()],key=lambda s:s['bbox'][0])
                        if not items:continue
                        line_size=statistics.median(s['size'] for s in items)*sy
                        groups=[]
                        for span in items:
                            if not groups or (span['bbox'][0]-groups[-1][-1]['bbox'][2])*sx>line_size*2.5:groups.append([])
                            groups[-1].append(span)
                        for group in groups:
                            text=' '.join(s['text'].strip() for s in group)
                            x0=min(s['bbox'][0] for s in group)*sx;x1=max(s['bbox'][2] for s in group)*sx
                            baseline=statistics.median(s['origin'][1] for s in group)*sy-line_size*.25
                            origin=fitz.Point(x0,baseline);width=font.text_length(text,fontsize=line_size)
                            if width<=0:continue
                            runs.append(dict(text=text,origin=origin,size=line_size,width=width,bbox=(x0,min(s['bbox'][1] for s in group)*sy,x1,max(s['bbox'][3] for s in group)*sy)))
                    for run in reading_order(runs,page.rect.width):
                        origin=run['origin'];x0,y0,x1,y1=run['bbox']
                        normalized.insert_text(origin,run['text'],fontsize=run['size'],fontname='helv',
                            morph=(origin,fitz.Matrix((x1-x0)/run['width'],1)))
                pending=cache/('page-'+str(i+1)+'-'+uuid.uuid4().hex+'.pdf')
                with fitz.open() as one:
                    one.insert_pdf(result,from_page=len(result)-1,to_page=len(result)-1)
                    one.save(pending,garbage=4,deflate=True,clean=False)
                sha=digest(pending);pending.replace(cached)
                save(manifest,dict(signature=signature,sha256=sha))
                done.append(i)
            else:
                result.insert_pdf(doc,from_page=i,to_page=i)
                from .pdf_preservation import copy_group
                copy_group(doc,page,result,result[-1])
                if i in rotated:
                    # Translate horizontal native text in its canonical page
                    # coordinates, then restore metadata rotation on export.
                    directions=[(line.get('dir',(1,0)),sum(len(s['text']) for s in line['spans'])) for block in page.get_text('dict')['blocks'] for line in block.get('lines',[])]
                    horizontal=sum(n for (x,y),n in directions if abs(x)>.8)
                    vertical=sum(n for (x,y),n in directions if abs(y)>.8)
                    if horizontal>max(10,vertical*2):
                        result[-1].set_rotation(0);restore=page.rotation
                    else:
                        result[-1].remove_rotation();restore=0
                    transforms.append(dict(source_page=i+1,original_rotation=page.rotation,restore_rotation=restore))
        result.set_metadata(doc.metadata)
        result.set_toc(doc.get_toc())
    result.save(destination,garbage=4,deflate=True,clean=False);result.close()
    save(report_path,dict(pages=transforms,ocr_cache=dict(hits=cache_hits,created=len(done)-cache_hits)));return done


def reading_order(runs,width):
    # OCR stream order can alternate left/right on every physical line. Require
    # repeated substantial lines in both columns before serializing by column.
    candidates=[r for r in runs if width*.25<r['bbox'][2]-r['bbox'][0]<width*.55]
    anchors=[]
    for item in sorted(candidates,key=lambda r:r['bbox'][0]):
        if not anchors or item['bbox'][0]-anchors[-1][0]['bbox'][0]>width*.12:anchors.append([])
        anchors[-1].append(item)
    anchors=[g for g in anchors if len(g)>=3]
    if len(anchors)!=2 or anchors[1][0]['bbox'][0]-anchors[0][0]['bbox'][0]<width*.25:
        return sorted(runs,key=lambda r:(r['bbox'][1],r['bbox'][0]))
    gap=(max(r['bbox'][2] for r in anchors[0])+min(r['bbox'][0] for r in anchors[1]))/2
    wide=[r for r in runs if r['bbox'][0]<gap<r['bbox'][2]]
    boundaries=sorted(r['bbox'][1] for r in wide)
    def key(run):
        x0,y0,x1,y1=run['bbox']
        if run in wide:band=2*sum(y0>y for y in boundaries)+1
        else:band=2*sum(y0>y for y in boundaries)
        return band,0 if run in wide else (1 if (x0+x1)/2<gap else 2),y0,x0
    return sorted(runs,key=key)
