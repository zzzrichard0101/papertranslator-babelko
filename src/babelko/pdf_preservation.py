"""Preserve page transparency and navigation without rewriting content streams."""
import re
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
