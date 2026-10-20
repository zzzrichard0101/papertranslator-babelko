import re
import pymupdf as fitz


def inspect_output(path,selected):
    issues=[];pages=[]
    with fitz.open(path) as doc:
        if len(doc)!=len(selected):issues.append(dict(code='page_count'))
        for i,page in enumerate(doc):
            text=page.get_text();spans=[s for b in page.get_text('dict')['blocks'] if 'lines' in b for l in b['lines'] for s in l['spans']]
            overflow=[s for s in spans if s['bbox'][0]<-.5 or s['bbox'][1]<-.5 or s['bbox'][2]>page.rect.width+.5 or s['bbox'][3]>page.rect.height+.5]
            if overflow:issues.append(dict(code='outside_page',page=i+1,count=len(overflow)))
            if '\ufffd' in text:issues.append(dict(code='replacement_glyph',page=i+1))
            pages.append(dict(source_page=selected[i]+1,korean_characters=len(re.findall(r'[가-힣]',text)),text_characters=len(text),outside_page=len(overflow)))
    return dict(status='passed' if not issues else 'failed',scope='page count, glyph extraction and page bounds; not semantic or full overlap certification',issues=issues,pages=pages)



def tracking_status(path):
    from .storage import read
    if not path.exists():return dict(status='failed',parsed_translation_units=0,units_with_no_output=0,reason='translation tracker missing')
    found=[]
    def visit(value):
        if isinstance(value,dict):
            if 'pdf_unicode' in value and value.get('input'):found.append(value)
            else:
                for child in value.values():visit(child)
        elif isinstance(value,list):
            for child in value:visit(child)
    visit(read(path))
    missing=[v for v in found if not v.get('output')]
    return dict(status='passed' if not missing else 'failed',parsed_translation_units=len(found),units_with_no_output=len(missing),
        scope='BabelDOC tracked translation inputs; not OCR recall or independent semantic coverage')
