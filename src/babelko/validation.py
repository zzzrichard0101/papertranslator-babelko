import re
import pymupdf as fitz


def inspect_output(path,selected,extracted_pages=None,source_path=None):
    issues=[];pages=[]
    inherited=[]
    if source_path is not None:
        with fitz.open(source_path) as source:
            for source_index in selected:
                source_page=source[source_index]
                inherited.append(source_page.get_text(textpage=source_page.get_textpage(flags=fitz.TEXTFLAGS_TEXT)).count('\ufffd'))
    with fitz.open(path) as doc:
        if len(doc)!=len(selected):issues.append(dict(code='page_count'))
        for i,page in enumerate(doc):
            # Match PyMuPDF's ordinary text extraction flags. Its bare
            # get_textpage() omits TEXT_USE_CID_FOR_UNKNOWN_UNICODE, turning
            # preserved font CIDs into U+FFFD despite a valid visible glyph.
            textpage=page.get_textpage(flags=fitz.TEXTFLAGS_TEXT);text=page.get_text(textpage=textpage)
            if extracted_pages is not None:extracted_pages.append(text)
            spans=[s for b in page.get_text('dict',textpage=textpage)['blocks'] if 'lines' in b for l in b['lines'] for s in l['spans']]
            # Text extraction uses unrotated page coordinates; page.rect is in
            # display coordinates. Compare in one space, including rotated PDFs.
            display=[fitz.Rect(s['bbox'])*page.rotation_matrix for s in spans]
            overflow=[box for box in display if not (page.rect+(-.5,-.5,.5,.5)).contains(box)]
            if overflow:issues.append(dict(code='outside_page',page=i+1,count=len(overflow)))
            replacement_count=text.count('\ufffd')
            source_count=inherited[i] if i<len(inherited) else 0
            if replacement_count>source_count:
                issues.append(dict(code='new_replacement_glyph',page=i+1,count=replacement_count-source_count))
            pages.append(dict(source_page=selected[i]+1 if i<len(selected) else None,korean_characters=len(re.findall(r'[가-힣]',text)),text_characters=len(text),outside_page=len(overflow),inherited_replacement_glyphs=min(replacement_count,source_count)))
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
    missing=[v for v in found if not isinstance(v.get('output'),str) or not v['output'].strip()]
    return dict(status='passed' if found and not missing else 'failed',parsed_translation_units=len(found),units_with_no_output=len(missing),
        reason='no tracked translation inputs' if not found else None,
        scope='BabelDOC tracked translation inputs; not OCR recall or independent semantic coverage')
