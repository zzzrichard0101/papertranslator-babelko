"""Conservative bibliography detection and native glyph preservation.

References are document data. A heading alone is insufficient to exempt prose:
require citation structure, and stop at the next substantive section heading.
"""
import hashlib,re
from contextlib import contextmanager
from unittest.mock import patch
from .storage import save

REVISION='bibliography-original-and-contents-15'
TAGS=re.compile(r'<[^>]+>')
HEADING=re.compile(r'^(?:(?:\d+(?:\.\d+)*|[A-Z])\.?\s+)?(?:references|bibliography|works cited|literature cited|참고\s*문헌)\s*[:.]?$',re.I)
AUTHOR_YEAR=re.compile(r"\b[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÿ’'\-]+,\s+(?:[A-Z]\.\s*){1,3}(?:(?:,?\s*&\s*|,\s*)[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÿ’'\-]+,\s*(?:[A-Z]\.\s*){1,3})?\s*(?:\(Ed(?:s)?\.\)\.\s*)?\((?:18|19|20)\d{2}[a-z]?\)\.")
# Numeric labels in camera-ready papers usually precede full given names,
# not APA surnames. A clipped column may also lose the opening '['.
NUMBERED=re.compile(r'^\s*(?:\[\d+\]|\d+\]|\d+\.)\s+(?:[A-Z]\.\s*)*[A-Z][A-Za-z’\'\-]+(?:\s+[A-Z][A-Za-z’\'\-]+){0,3}(?:,|\s+[A-Z]\.)')
METADATA=re.compile(r'https?://doi\.org/|\bdoi\s*:|\barxiv\b|\babs/\d{4}\.\d{4,5}\b|\b\d+\s*\(\d+\)\s*[,.:]|\b(?:pp\.|vol\.|press\b|publisher\b)|\b[A-Z]{2}:\s*[A-Z]',re.I)
ARXIV_ID=re.compile(r'\babs/\d{4}\.\d{4,5}\b',re.I)
# Some extractors merge an entire numbered bibliography column into one
# paragraph, leaving its first citation split across several IL paragraphs.
FUSED_NUMBERED=re.compile(r'(?:^|[.!?]\s+)\d{1,3}\.\s+[A-Z][A-Za-z’\'\-]+,\s*(?:[A-Z]\.|[A-Z][a-z])')
BRACKETED_ANCHOR=re.compile(r'\[\d{1,3}\]\s+[A-Z][A-Za-zÀ-ÿ’\'\-]+,\s*[A-Z]\.')
BRACKETED_FULLNAME=re.compile(r'\[\d{1,3}\]\s+(?:[A-Z]\.?(?:\s+|(?=[A-Z]))){0,2}[A-Z][A-Za-zÀ-ÿ’\'\-]+(?:\s+[A-Z][A-Za-zÀ-ÿ’\'\-]+){1,3}[,.]')
JOURNAL_PAGES=re.compile(r'\b\d{1,4}\s*,\s*\d{2,6}(?:[-–]\d+)?\s*\((?:18|19|20)\d{2}\)')
AUTHOR_INITIALS=re.compile(r"\b[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÿ’'\-]+,\s*(?:[A-Z]\.\s*){1,3}")
YEAR_JOURNAL=re.compile(r'\b(?:18|19|20)\d{2}[a-z]?,\s*[A-Z][A-Za-z.]{1,12},\s*\d{1,5}\b')
ARXIV_PREPRINT=re.compile(r'\barxiv\s*(?:preprint\s*)?(?:arxiv\s*)?:\s*\d{4}\.\d{4,5}\b',re.I)
AUTHOR_BIO=re.compile(r'^[A-Z][A-Z .\-]{9,}\s+(?:\([^)]*IEEE\)\s+)?(?:received|obtained|earned|is currently|was born)\b',re.I)
NON_REFERENCE=re.compile(r'^(?:fig(?:ure)?\.?\s*[A-Z]?\d+[.:\s]|table\s*[A-Z]?\d+[.:\s]|publisher[’\']s\s+note\b|we\s+(?:compare|show|demonstrate|analyze|analyse|propose|evaluate|discuss)\b)',re.I)


def text(paragraph):
    return re.sub(r'\s+',' ',TAGS.sub('',getattr(paragraph,'unicode','') or '')).strip()


def entry(value):
    """Recognize complete entries, never a bare in-text author/year citation."""
    value=re.sub(r'\s+',' ',TAGS.sub('',value)).strip();matches=list(AUTHOR_YEAR.finditer(value))
    # OCR can start a reference block mid-entry, or interleave its first author
    # with another line. Repeated author/year anchors plus publication metadata
    # establish a bibliography even when its first characters are damaged.
    damaged_block=len(matches)>=2 and bool(METADATA.search(value)) and len(value)/len(matches)<650
    # A PDF extractor can fuse a whole numbered reference column into one
    # paragraph and replace its [n] markers with formula placeholders.  A
    # clipped carry-over may then start with "abs/..." rather than an author.
    # Multiple distinct arXiv records with publication years are stronger
    # evidence than the paragraph's damaged first token.
    arxiv_ids=set(ARXIV_ID.findall(value))
    fused_arxiv_block=(len(arxiv_ids)>=2 and len(re.findall(r'\b(?:18|19|20)\d{2}\b',value))>=2
                       and len(value)/len(arxiv_ids)<900)
    numbered=list(FUSED_NUMBERED.finditer(value))
    fused_numbered_block=(len(numbered)>=2 and len(re.findall(r'\b(?:18|19|20)\d{2}\b',value))>=2
                          and len(value)/len(numbered)<900 and bool(METADATA.search(value)))
    bracketed=list(BRACKETED_ANCHOR.finditer(value))
    fused_bracketed_block=(len(bracketed)>=2 and len(re.findall(r'\b(?:18|19|20)\d{2}\b',value))>=2
                            and len(value)/len(bracketed)<900 and bool(METADATA.search(value) or JOURNAL_PAGES.search(value)))
    fullnames=list(BRACKETED_FULLNAME.finditer(value))
    fused_fullname_block=(len(fullnames)>=2 and len(re.findall(r'\b(?:18|19|20)\d{2}\b',value))>=2
                          and len(value)/len(fullnames)<900 and bool(METADATA.search(value) or JOURNAL_PAGES.search(value)))
    # Camera-ready PDFs can fuse an entire unnumbered bibliography column.
    # Demand repeated publication records and dense citation structure; years
    # or author mentions alone are not enough to exempt ordinary prose.
    years=re.findall(r'\b(?:18|19|20)\d{2}[a-z]?\b',value)
    initials=AUTHOR_INITIALS.findall(value)
    fused_publications=(len(years)>=3 and len(value)/len(years)<350 and (
        (len(ARXIV_PREPRINT.findall(value))>=3 and len(re.findall(r'\{v\d+\}',value))>=3)
        or (len(JOURNAL_PAGES.findall(value))>=3 and len(initials)>=3)
        or (len(YEAR_JOURNAL.findall(value))>=3 and len(initials)>=6)))
    return bool(damaged_block or fused_arxiv_block or fused_numbered_block or fused_bracketed_block or
                fused_fullname_block or
                fused_publications or
                (matches and matches[0].start()==0 and (len(matches)>1 or METADATA.search(value))) or
                (NUMBERED.match(value) and re.search(r'\b(?:18|19|20)\d{2}\b',value) and
                 (METADATA.search(value) or JOURNAL_PAGES.search(value))))


def select(docs):
    selected=[];active=False
    pages=list(docs.page)
    page_values=[[text(p) for p in getattr(page,'pdf_paragraph',[])] for page in pages]
    def dense_index(values):
        combined=' '.join(values)
        return (len(re.findall(r'(?<![A-Za-z0-9])\d{1,4}(?:\s*[-–]\s*\d{1,4})?(?![A-Za-z0-9])',combined))>=40
            and not any(entry(value) for value in values))
    dense=[dense_index(values) for values in page_values]
    index_pages={i for i,values in enumerate(page_values) if dense[i] and any(
        re.fullmatch(r'(?:\d{1,4}\s+)?Index',value,re.I) for value in values)}
    # A first index page may have a visual title that the text layer misses.
    # Its many locator numbers and the next page's explicit Index header give
    # document-level evidence without assuming every numbered page is an index.
    for seed in sorted(index_pages):
        # Running "Index" headers may be missing on several initial scan
        # pages. Walk through contiguous locator-dense pages, bounded so an
        # unrelated numbered appendix cannot be swallowed indefinitely.
        i=seed
        for _ in range(12):
            if not i or not dense[i-1]:break
            i-=1;index_pages.add(i)
    for i in range(1,len(pages)):
        if i-1 in index_pages and dense[i]:index_pages.add(i)
    for page_index,page in enumerate(pages):
        paragraphs=getattr(page,'pdf_paragraph',[])
        values=page_values[page_index]
        if page_index in index_pages:
            selected.extend((page,p,'index_section') for p in paragraphs)
            active=False
            continue
        bridge_until=-1
        # A new page cannot inherit a bibliography exemption just because an
        # OCR heading was missed. Require fresh entry evidence on that page.
        if active and not any(entry(v) for v in values):active=False
        for i,(p,value) in enumerate(zip(paragraphs,values)):
            # A clipped citation at the top of a continuing reference page
            # can be marked "abandon" by layout analysis even though native
            # translation still sees it. Keep it original, but not page nums.
            if getattr(p,'layout_label','')=='abandon' and not (active and value and not value.isdigit()):
                continue
            heading=bool(HEADING.fullmatch(value))
            # A scanned separator or damaged running title can sit between a
            # bibliography heading and its first real citation. Its text is
            # not trustworthy, but the following citation establishes scope.
            next_entries=[k for k in range(i+1,min(len(values),i+9)) if entry(values[k])]
            section_title=bool(re.match(r'^(?:appendix|chapter|discussion|conclusion)\b',value,re.I))
            heading_bridge=(getattr(p,'layout_label','')=='title' and not heading and
                (i<=bridge_until or bool(next_entries)) and not section_title)
            # IEEE author biographies often follow references on the same
            # page without a section title. Do not exempt or translate them as
            # part of the bibliography just because the heading remains active.
            if active and AUTHOR_BIO.match(value):active=False
            if heading:
                # A table of contents entry does not open an exempt section.
                candidates=[]
                for k in next_entries:
                    if any(getattr(paragraphs[m],'layout_label','')=='title' and
                        re.match(r'^(?:appendix|chapter|discussion|conclusion)\b',values[m],re.I)
                        for m in range(i+1,k)):continue
                    candidates.append(k)
                active=bool(candidates);bridge_until=min(candidates) if candidates else -1
            elif getattr(p,'layout_label','')=='title' and value and not entry(value) and not (active and heading_bridge):
                active=False
            standalone=entry(value)
            # Captions, publisher notices and clear first-person prose can
            # appear inside the physical reference region. They are distinct
            # document content even if citations resume in the next column.
            if active and not standalone and NON_REFERENCE.match(value):continue
            if heading and active or standalone or active and value:
                selected.append((page,p,'reference_section' if active else 'citation_structure'))
    # A compact appendix contents block is sometimes printed above the first
    # real appendix section on the same page. Its leader dots and right-aligned
    # page locators may be fused into giant PDF paragraphs. Translating such a
    # paragraph destroys the rows; retain the exact original glyphs until a
    # verified row-preserving compositor is available.
    known={id(p) for _,p,_ in selected}
    for page in pages:
        paragraphs=getattr(page,'pdf_paragraph',[])
        values=[text(p) for p in paragraphs]
        for start,value in enumerate(values):
            if not re.fullmatch(r'Appendix|Appendices',value,re.I) or getattr(paragraphs[start],'layout_label','')!='title':continue
            end=next((i for i in range(start+1,len(values)) if getattr(paragraphs[i],'layout_label','')=='title'
                and re.match(r'^[A-Z]\.\s+',values[i])),None)
            if end is None:continue
            if sum(bool(re.search(r'(?:\s*\.\s*){8,}',item)) for item in values[start+1:end])<2:continue
            for p in paragraphs[start+1:end]:
                if id(p) not in known:selected.append((page,p,'appendix_contents'));known.add(id(p))
            break
    # Running matter is often split differently on each page. Sending a
    # repeated long header to the model can make it duplicate the translated
    # title and spill over the top margin. Leave source glyphs in place when
    # the same abandoned text recurs on separate pages.
    repeated={}
    for page in pages:
        for p in getattr(page,'pdf_paragraph',[]):
            value=text(p)
            if getattr(p,'layout_label','')=='abandon' and len(value)>=45:
                repeated.setdefault(value,[]).append((page,p))
    for occurrences in repeated.values():
        if len({id(page) for page,_ in occurrences})<2:continue
        for page,p in occurrences:
            if id(p) not in known:selected.append((page,p,'repeated_running_matter'));known.add(id(p))
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
