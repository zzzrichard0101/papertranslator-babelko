"""Local searchable input for scans; original PDF remains separate."""
import math,os
from pathlib import Path
import pymupdf as fitz
from .storage import digest
OCR_SHA='8280aed0782fe27257a68ea10fe7ef324ca0f8d85bd2fd145d1c2b560bcb66ba'


def data_path():
    from .storage import root
    candidates=[root()/'assets/ocr',Path(os.environ['LOCALAPPDATA'])/'PaperTranslator/app-v0.5.10a1/_internal/papertranslator/ocr_models']
    return next((p for p in candidates if (p/'eng.traineddata').is_file()),None)


def prepare(source,destination,mode='auto',progress=print,cancel=lambda:False,selected=None):
    if mode not in {'auto','off','force'}:raise ValueError('OCR 설정 오류')
    done=[];result=fitz.open()
    with fitz.open(source) as doc:
        for i,page in enumerate(doc):
            if cancel():raise InterruptedError('취소됨')
            image_area=sum((fitz.Rect(x['bbox']) & page.rect).get_area() for x in page.get_image_info())
            scanned=len(page.get_text().strip())<100 and image_area>page.rect.get_area()*.6
            if (selected is None or i in selected) and (mode=='force' or (mode=='auto' and scanned)):
                data=data_path()
                if not data or digest(data/'eng.traineddata')!=OCR_SHA:raise RuntimeError('검증된 영어 OCR 데이터가 필요합니다. 설정 준비를 다시 실행하세요.')
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
                done.append(i)
            else:result.insert_pdf(doc,from_page=i,to_page=i)
    result.save(destination);result.close();return done


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
