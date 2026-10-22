"""Occurrence-based source -> model record -> typeset glyph -> PDF ledger.

This measures survival of the ANALYZED source catalog, not OCR recall or truth.
Equal paragraphs in different cells/pages are distinct occurrences. Translation
cache keys remain content-based and may legitimately be shared by occurrences.
"""
import collections,hashlib,json,math,re,threading
from contextlib import contextmanager
from dataclasses import fields,is_dataclass
from unittest.mock import patch
import pymupdf as fitz
from .storage import read,save
from .render_coverage import TOKENS,canonical

REVISION='spatial-occurrences-1'


def box(value):
    if value is None:return None
    return [round(float(getattr(value,k)),4) for k in ('x','y','x2','y2')]


def characters(value,seen=None):
    from babeldoc.format.pdf.document_il import PdfCharacter
    seen=set() if seen is None else seen
    if value is None or id(value) in seen:return
    seen.add(id(value))
    if isinstance(value,PdfCharacter):
        if value.box and value.char_unicode:yield value
    elif isinstance(value,list):
        for child in value:yield from characters(child,seen)
    elif is_dataclass(value):
        for field in fields(value):
            child=getattr(value,field.name)
            if isinstance(child,list) or is_dataclass(child):yield from characters(child,seen)


class RegionLedger:
    def __init__(self,folder):
        self.folder=folder;self.rows=[];self.by_object={};self.collecting=False
        self.source_sha256=read(folder/'state.json').get('source_sha256') if (folder/'state.json').is_file() else None
        self.lock=threading.RLock();self.unknown=[];self.records={};self.source_records=collections.defaultdict(dict)

    def begin(self,docs):
        from .references import select
        references={id(p) for _,p,_ in select(docs)}
        self.rows=[];self.by_object={};self.unknown=[];self.records={};self.source_records=collections.defaultdict(dict)
        occurrences=collections.Counter()
        for page in docs.page:
            for paragraph in page.pdf_paragraph:
                text=paragraph.unicode or ''
                if not canonical(text):continue
                position=box(paragraph.box)
                payload=[REVISION,self.source_sha256,page.page_number,position,paragraph.layout_label,text]
                identity=hashlib.sha256(json.dumps(payload,ensure_ascii=False).encode()).hexdigest()
                ordinal=occurrences[identity];occurrences[identity]+=1
                row=dict(id=identity+'-'+str(ordinal),source_page=page.page_number+1,
                    source_box=position,role=paragraph.layout_label,source=text,inputs=[],record_keys=[],target=None,
                    policy='preserved_reference' if id(paragraph) in references else 'translate',debug_id=paragraph.debug_id)
                self.rows.append(row);self.by_object[id(paragraph)]=row
        self.collecting=True

    def pre(self,paragraph,text):
        if not self.collecting:return
        row=self.by_object.get(id(paragraph))
        with self.lock:
            # BabelDOC can create punctuation-only drawing fragments after the
            # source catalog is frozen. They contain no translatable content.
            if row is None:
                if canonical(paragraph.unicode or ''):
                    self.unknown.append(dict(debug_id=paragraph.debug_id,source=paragraph.unicode))
                return
            if text and text not in row['inputs']:row['inputs'].append(text)

    def link(self,record):
        if not self.collecting:return
        with self.lock:
            self.records[record['key']]=record
            self.source_records[record['source'].strip()][record['key']]=record

    def post(self,paragraph,text):
        if not self.collecting:return
        row=self.by_object.get(id(paragraph))
        if row is not None:
            from .hybrid import split_source
            # Native batch inference and paragraph preparation run in different
            # workers. Bind by exact source parts AND the returned target, not
            # thread-local state or a deduplicated content occurrence ID.
            with self.lock:
                row['target']=text;row['record_keys']=[];keys=[];cursor=0;whole=canonical(text)
                for part in split_source(row['inputs'][-1]) if row['inputs'] else []:
                    choices=[r for r in self.source_records.get(part.strip(),{}).values() if r.get('final') is not None]
                    matches=[r for r in choices if whole.startswith(canonical(r['final']),cursor)]
                    pieces={canonical(r['final']) for r in matches}
                    if len(pieces)!=1:break
                    piece=next(iter(pieces));cursor+=len(piece);keys.extend(r['key'] for r in matches)
                else:
                    if cursor==len(whole):row['record_keys']=sorted(set(keys))

    def typeset(self,docs):
        # Capture final positions AFTER native page fitting and font selection.
        for page in docs.page:
            for paragraph in page.pdf_paragraph:
                row=self.by_object.get(id(paragraph))
                if row is None:continue
                row['planned_box']=box(paragraph.box)
                row['glyphs']=[dict(text=c.char_unicode,box=box(c.box)) for c in characters(paragraph.pdf_paragraph_composition)]
        save(self.folder/'region-ledger.json',dict(revision=REVISION,source_sha256=self.source_sha256,regions=self.rows,unmapped=self.unknown))

    def inspect(self,path,selected,source_path=None):
        issues=[];checked=0;glyph_count=0
        if self.unknown:issues.append(dict(code='unmapped_translation',count=len(self.unknown)))
        page_map={source+1:target for target,source in enumerate(selected)}
        with fitz.open(path) as pdf:
            pools=[];used=[set() for _ in pdf]
            for page in pdf:
                pool=collections.defaultdict(list)
                textpage=page.get_textpage()
                for block in page.get_text('rawdict',textpage=textpage)['blocks']:
                    for line in block.get('lines',[]):
                        for span in line.get('spans',[]):
                            for char in span.get('chars',[]):
                                x0,y0,x1,y1=char['bbox'];x=(x0+x1)/2;y=(y0+y1)/2
                                for c in ('\ufffd' if char['c']=='\ufffd' else canonical(char['c'])):
                                    item=(glyph_count,c,x,y)
                                    glyph_count+=1;pool[(math.floor(x/16),math.floor(y/16),c)].append(item)
                pools.append(pool)
            source_pdf=fitz.open(source_path) if source_path is not None else None
            try:
              for row in self.rows:
                page_index=page_map.get(row['source_page'])
                if page_index is None:continue
                problems=[];target=row['target'];glyphs=row.get('glyphs',[])
                if row['policy']=='translate':
                    # Bare numbers, formulas and code can follow the native
                    # preservation path. English prose cannot silently do so.
                    if (not row['inputs'] and row['role'] not in {'fallback_line','abandon'}
                            and any(c.isalpha() and c.isascii() for c in row['source'])):
                        problems.append('source_region_not_submitted')
                    elif row['inputs'] and target is None:problems.append('translation_not_replayed')
                    elif row['inputs'] and not row['record_keys']:problems.append('translation_record_not_linked')
                expected=canonical(TOKENS.sub('',target if target is not None else row['source']))
                produced=canonical(''.join(g['text'] for g in glyphs))
                if collections.Counter(expected)-collections.Counter(produced):problems.append('typeset_text_missing')
                missing=0;needed=0
                page=pdf[page_index];height=page.mediabox.height
                preserved_abandon=False
                if source_pdf is not None and row['role']=='abandon' and not row['inputs'] and row['source_box']:
                    # Rotated metadata may use glyph coordinates that are not
                    # directly comparable with extraction boxes. Demand exact
                    # pixel preservation of that source region instead.
                    x0,y0,x1,y1=row['source_box']
                    clip=fitz.Rect(x0-2,height-y1-2,x1+2,height-y0+2)
                    original=source_pdf[row['source_page']-1].get_pixmap(clip=clip,colorspace=fitz.csGRAY,alpha=False)
                    rendered=page.get_pixmap(clip=clip,colorspace=fitz.csGRAY,alpha=False)
                    preserved_abandon=(original.width==rendered.width and original.height==rendered.height
                                       and original.samples==rendered.samples)
                for glyph in ([] if preserved_abandon else glyphs):
                    x0,y0,x1,y1=glyph['box'];x=(x0+x1)/2;y=height-(y0+y1)/2
                    # PDF extraction boxes are font ascenders, while the IL
                    # boxes are advance-height boxes. The baseline offset can
                    # exceed two points for small chart labels, even when the
                    # glyph's actual x/y position is unchanged.
                    tolerance=max(4.,abs(y1-y0)*.5)
                    cid_glyph=bool(re.fullmatch(r'\(cid:\d+\)',glyph['text']))
                    for c in ('\ufffd' if cid_glyph else canonical(glyph['text'])):
                        needed+=1;options=[]
                        if cid_glyph:tolerance=max(tolerance,7.)
                        for gx in range(math.floor((x-tolerance)/16),math.floor((x+tolerance)/16)+1):
                            for gy in range(math.floor((y-tolerance)/16),math.floor((y+tolerance)/16)+1):
                                for item in pools[page_index].get((gx,gy,c),[]):
                                    if item[0] not in used[page_index] and abs(item[2]-x)<=tolerance and abs(item[3]-y)<=tolerance:
                                        options.append(((item[2]-x)**2+(item[3]-y)**2,item[0]))
                        if options:used[page_index].add(min(options)[1])
                        else:missing+=1
                if missing:problems.append('pdf_glyph_missing_or_moved')
                checked+=1
                if problems:issues.append(dict(region_id=row['id'],source_page=row['source_page'],source_box=row['source_box'],
                    role=row['role'],codes=problems,missing_glyphs=missing,expected_glyphs=needed,record_keys=row['record_keys']))
            finally:
                if source_pdf is not None:source_pdf.close()
        report=dict(revision=REVISION,status='failed' if issues else 'passed',checked_regions=checked,
            preserved_references=sum(r['policy']=='preserved_reference' for r in self.rows),issues=issues,
            scope='Analyzed source occurrences, replay, typeset text counts and per-glyph PDF positions. Not OCR recall, reading order or semantic certification.')
        save(self.folder/'region-coverage.json',report);return report


@contextmanager
def capture(ledger):
    from babeldoc.format.pdf.document_il.midend.il_translator import ILTranslator
    from babeldoc.format.pdf.document_il.midend.typesetting import Typesetting
    pre=ILTranslator.pre_translate_paragraph;post=ILTranslator.post_translate_paragraph;typeset=Typesetting.typesetting_document
    def before(self,paragraph,*args,**kwargs):
        value=pre(self,paragraph,*args,**kwargs);ledger.pre(paragraph,value[0]);return value
    def after(self,paragraph,tracker,translate_input,translated_text):
        result=post(self,paragraph,tracker,translate_input,translated_text);ledger.post(paragraph,translated_text);return result
    def fitted(self,document):
        result=typeset(self,document);ledger.typeset(document);return result
    with patch.object(ILTranslator,'pre_translate_paragraph',before),patch.object(ILTranslator,'post_translate_paragraph',after),patch.object(Typesetting,'typesetting_document',fitted):yield
