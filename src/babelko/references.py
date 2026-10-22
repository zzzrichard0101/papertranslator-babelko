"""Conservative bibliography detection and native glyph preservation.

References are document data. A heading alone is insufficient to exempt prose:
require citation structure, and stop at the next substantive section heading.
"""
import hashlib,re
from contextlib import contextmanager
from unittest.mock import patch
from .storage import save

REVISION='bibliography-original-2'
TAGS=re.compile(r'<[^>]+>')
HEADING=re.compile(r'^(?:(?:\d+(?:\.\d+)*|[A-Z])\.?\s+)?(?:references|bibliography|works cited|literature cited|참고\s*문헌)\s*[:.]?$',re.I)
AUTHOR_YEAR=re.compile(r"\b[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÿ’'\-]+,\s+(?:[A-Z]\.\s*){1,3}(?:(?:,?\s*&\s*|,\s*)[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÿ’'\-]+,\s*(?:[A-Z]\.\s*){1,3})?\s*(?:\(Ed(?:s)?\.\)\.\s*)?\((?:18|19|20)\d{2}[a-z]?\)\.")
NUMBERED=re.compile(r'^\s*(?:\[\d+\]|\d+\.)\s+(?:[A-Z]\.\s*)*[A-Z][A-Za-z’\'\-]+(?:,|\s+[A-Z]\.)')
METADATA=re.compile(r'https?://doi\.org/|\bdoi\s*:|\b\d+\s*\(\d+\)\s*[,.:]|\b(?:pp\.|vol\.|press\b|publisher\b)|\b[A-Z]{2}:\s*[A-Z]',re.I)


def text(paragraph):
    return re.sub(r'\s+',' ',TAGS.sub('',getattr(paragraph,'unicode','') or '')).strip()


def entry(value):
    """Recognize complete entries, never a bare in-text author/year citation."""
    value=re.sub(r'\s+',' ',TAGS.sub('',value)).strip();matches=list(AUTHOR_YEAR.finditer(value))
    # OCR can start a reference block mid-entry, or interleave its first author
    # with another line. Repeated author/year anchors plus publication metadata
    # establish a bibliography even when its first characters are damaged.
    damaged_block=len(matches)>=2 and bool(METADATA.search(value)) and len(value)/len(matches)<650
    return bool(damaged_block or (matches and matches[0].start()==0 and (len(matches)>1 or METADATA.search(value))) or
                (NUMBERED.match(value) and re.search(r'\b(?:18|19|20)\d{2}\b',value) and METADATA.search(value)))


def select(docs):
    selected=[];active=False
    for page in docs.page:
        paragraphs=getattr(page,'pdf_paragraph',[])
        values=[text(p) for p in paragraphs]
        # A new page cannot inherit a bibliography exemption just because an
        # OCR heading was missed. Require fresh entry evidence on that page.
        if active and not any(entry(v) for v in values):active=False
        for i,(p,value) in enumerate(zip(paragraphs,values)):
            heading=bool(HEADING.fullmatch(value))
            if heading:
                upcoming=[]
                for q,v in zip(paragraphs[i+1:],values[i+1:]):
                    if getattr(q,'layout_label','')=='title' and not HEADING.fullmatch(v):break
                    upcoming.append(v)
                # A table of contents entry does not open an exempt section.
                active=any(entry(v) for v in upcoming)
            elif getattr(p,'layout_label','')=='title' and value and not entry(value):
                active=False
            standalone=entry(value)
            if heading and active or standalone or active and value:
                selected.append((page,p,'reference_section' if active else 'citation_structure'))
    return selected


@contextmanager
def preserve(folder):
    """Filter references before cross-page merging; leave original IL untouched.

    Both native passes and the single-model path use the same policy. Keeping
    the original compositions avoids rebuilding reference typography at all.
    """
    from babeldoc.format.pdf.document_il.midend.il_translator_llm_only import ILTranslatorLLMOnly as Native
    original_translate=Native.translate
    original_filter=Native._should_translate_paragraph
    original_page=Native.process_page

    def translate(self,docs):
        chosen=select(docs);self._babelko_reference_ids={id(p) for _,p,_ in chosen}
        save(folder/'reference-preservation.json',dict(revision=REVISION,policy='original',
            paragraphs=[dict(source_page=getattr(page,'page_number',0)+1,debug_id=p.debug_id,
                sha256=hashlib.sha256(text(p).encode()).hexdigest(),reason=reason) for page,p,reason in chosen]))
        return original_translate(self,docs)

    def should_translate(self,paragraph,translated_ids=None,require_body_text=False):
        if id(paragraph) in getattr(self,'_babelko_reference_ids',set()):return False
        return original_filter(self,paragraph,translated_ids,require_body_text)

    def process_page(self,page,executor,pbar=None,tracker=None,executor2=None,translated_ids=None):
        if translated_ids is None:translated_ids=set()
        preserved={id(p) for p in page.pdf_paragraph}&getattr(self,'_babelko_reference_ids',set())
        new=preserved-translated_ids;translated_ids.update(preserved)
        if pbar and new:pbar.advance(len(new))
        return original_page(self,page,executor,pbar,tracker,executor2,translated_ids)

    with patch.object(Native,'translate',translate),patch.object(Native,'_should_translate_paragraph',should_translate),patch.object(Native,'process_page',process_page):yield
