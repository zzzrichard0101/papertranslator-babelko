"""Preserve page transparency and navigation without rewriting content streams."""
import re
from pathlib import Path
import pymupdf as fitz


def copy_group(source,page,target,new_page):
    kind,value=source.xref_get_key(page.xref,'Group')
    if kind=='xref':value=source.xref_object(int(value.split()[0]),compressed=False)
    # Direct dictionaries are portable. Never transplant foreign indirect xrefs.
    if kind!='null' and not re.search(r'\b\d+\s+\d+\s+R\b',value):
        target.xref_set_key(new_page.xref,'Group',value)


def optimize(source,destination):
    with fitz.open(source) as doc:
        # clean=True changes some source drawing operators; dedup only.
        doc.save(destination,garbage=4,deflate=True,clean=False)


def restore_original_index(original,korean,selected,reference_report):
    """Use original raster pages for an index exempt from translation.

    The scan's synthetic OCR overlay can otherwise be drawn on top of its
    original pixels, making even an untranslated index look doubled.
    """
    source_pages={item['source_page']-1 for item in reference_report.get('paragraphs',[])
        if item.get('reason')=='index_section'}
    if not source_pages:return []
    positions=[i for i,source in enumerate(selected) if source in source_pages]
    if not positions:return []
    korean=Path(korean);temporary=korean.with_name(korean.stem+'.index-restored.pdf')
    with fitz.open(original) as source,fitz.open(korean) as translated,fitz.open() as restored:
        if len(translated)!=len(selected):raise ValueError('색인 복구 전 PDF 쪽수 불일치')
        start=0
        while start<len(selected):
            use_source=start in positions;stop=start
            while stop+1<len(selected) and ((stop+1 in positions)==use_source) and (
                not use_source or selected[stop+1]==selected[stop]+1):stop+=1
            if use_source:restored.insert_pdf(source,from_page=selected[start],to_page=selected[stop],links=True)
            else:restored.insert_pdf(translated,from_page=start,to_page=stop,links=True)
            start=stop+1
        toc=translated.get_toc()
        if toc:restored.set_toc(toc)
        restored.set_metadata(translated.metadata)
        restored.save(temporary,garbage=4,deflate=True)
    temporary.replace(korean)
    return [selected[i]+1 for i in positions]
