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

REVISION='spatial-occurrences-2'


def box(value):
    if value is None:return None
    return [round(float(getattr(value,k)),4) for k in ('x','y','x2','y2')]


def visible_in_crop(source_box,page):
    """IL boxes use media-box bottom-left coordinates; CropBox is top-left."""
    if not source_box:return True
    x0,y0,x1,y1=source_box;crop=page.cropbox;height=page.mediabox.height
    return x1>crop.x0 and x0<crop.x1 and y1>height-crop.y1 and y0<height-crop.y0


def pixels_preserved(original,rendered):
    if original.width!=rendered.width or original.height!=rendered.height:return False
    if original.samples==rendered.samples:return True
    # A saved PDF can rerasterize a few antialiased edge pixels while leaving
    # a preserved rotated label intact. Never apply this allowance to a tiny
    # mark where losing one glyph could fit the tolerance.
    pairs=zip(original.samples,rendered.samples)
    source_dark=sum(value<160 for value in original.samples)
    if source_dark<200:return False
    changed=lost=added=0
    for before,after in pairs:
        changed+=before!=after
        lost+=before<160<=after
        added+=after<160<=before
    return (changed<=max(12,int(len(original.samples)*.005))
        and lost<=max(2,int(source_dark*.01))
        and added<=max(2,int(source_dark*.02)))


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
        self.saved_records=None

    def begin(self,docs):
        from .references import select
        from .figure_legends import select as select_figures
        references={id(p) for _,p,_ in select(docs)}
        figures,_=select_figures(docs)
        self.rows=[];self.by_object={};self.unknown=[];self.records={};self.source_records=collections.defaultdict(dict)
        self.saved_records=None
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
                    policy=('preserved_reference' if id(paragraph) in references else
                        'preserved_figure' if id(paragraph) in figures else 'translate'),debug_id=paragraph.debug_id)
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

    def saved_candidates(self,source):
        # Upstream may answer a repeated cell from its native cache without
        # calling our unit callback. Bind it to an exact active checkpoint.
        if self.saved_records is None:
            self.saved_records=collections.defaultdict(dict)
            order=self.folder/'unit-order.json'
            for key in (read(order).get('active_keys',[]) if order.is_file() else []):
                path=self.folder/'hybrid'/(key+'.json')
                if not path.is_file():continue
                record=read(path)
                if record.get('final') is not None:
                    self.saved_records[record['source'].strip()][key]=record
        return self.saved_records.get(source.strip(),{}).values()

    def relink_saved_row(self,row):
        if row['record_keys'] or not row['inputs'] or not isinstance(row['target'],str):return
        from .hybrid import split_source
        whole=canonical(row['target']);cursor=0;keys=[]
        parts=split_source(row['inputs'][-1])
        for index,part in enumerate(parts):
            matches=[r for r in self.saved_candidates(part) if whole.startswith(canonical(r['final']),cursor)
                and (index<len(parts)-1 or cursor+len(canonical(r['final']))==len(whole))]
            pieces={canonical(r['final']) for r in matches}
            if len(pieces)!=1:return
            piece=next(iter(pieces));cursor+=len(piece);keys.extend(r['key'] for r in matches)
        if cursor==len(whole):row['record_keys']=sorted(set(keys))

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
                parts=split_source(row['inputs'][-1]) if row['inputs'] else []
                for index,part in enumerate(parts):
                    choices=[r for r in self.source_records.get(part.strip(),{}).values() if r.get('final') is not None]
                    matches=[r for r in choices if whole.startswith(canonical(r['final']),cursor)
                        and (index<len(parts)-1 or cursor+len(canonical(r['final']))==len(whole))]
                    if not matches:
                        matches=[r for r in self.saved_candidates(part) if whole.startswith(canonical(r['final']),cursor)
                            and (index<len(parts)-1 or cursor+len(canonical(r['final']))==len(whole))]
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

    def inspect(self,path,selected,source_path=None,restored_index_pages=None,save_report=True):
        issues=[];checked=0;glyph_count=0
        if self.unknown:issues.append(dict(code='unmapped_translation',count=len(self.unknown)))
        page_map={source+1:target for target,source in enumerate(selected)}
        cid_pages={page_map[row['source_page']] for row in self.rows if row['source_page'] in page_map
            and any(re.fullmatch(r'\(cid:\d+\)',g['text']) for g in row.get('glyphs',[]))}
        with fitz.open(path) as pdf:
            pools=[];raw_pools=[];used=[set() for _ in pdf];used_cids=[set() for _ in pdf]
            for page_index,page in enumerate(pdf):
                pool=collections.defaultdict(list);raw_pool=collections.defaultdict(list)
                # The default TextPage substitutes some embedded-font CIDs
                # with U+FFFD. RAWDICT flags retain the actual PDF codepoints.
                textpage=page.get_textpage(flags=fitz.TEXTFLAGS_RAWDICT)
                for block in page.get_text('rawdict',textpage=textpage)['blocks']:
                    for line in block.get('lines',[]):
                        for span in line.get('spans',[]):
                            for char in span.get('chars',[]):
                                x0,y0,x1,y1=char['bbox'];x=(x0+x1)/2;y=(y0+y1)/2
                                raw_id=glyph_count;glyph_count+=1
                                if page_index in cid_pages:
                                    raw_pool[(math.floor(x/16),math.floor(y/16),char['c'])].append((raw_id,char['c'],x,y))
                                for offset,c in enumerate('\ufffd' if char['c']=='\ufffd' else canonical(char['c'])):
                                    item_id=raw_id if offset==0 else glyph_count
                                    if offset:glyph_count+=1
                                    pool[(math.floor(x/16),math.floor(y/16),c)].append((item_id,c,x,y))
                pools.append(pool);raw_pools.append(raw_pool)
            source_pdf=fitz.open(source_path) if source_path is not None else None
            try:
              verified_index=set()
              for source_page in sorted(set(restored_index_pages or [])):
                target_page=page_map.get(source_page)
                if target_page is None:continue
                if (source_pdf is not None and
                    source_pdf[source_page-1].get_pixmap(alpha=False).samples==pdf[target_page].get_pixmap(alpha=False).samples):
                    verified_index.add(source_page)
                else:issues.append(dict(source_page=source_page,code='restored_index_pixels_changed'))
              for row in self.rows:
                page_index=page_map.get(row['source_page'])
                if page_index is None:continue
                if row['source_page'] in verified_index:
                    checked+=1
                    continue
                source_page=source_pdf[row['source_page']-1] if source_pdf is not None else pdf[page_index]
                if not visible_in_crop(row['source_box'],source_page):continue
                self.relink_saved_row(row)
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
                page=pdf[page_index];height=page.mediabox.height;crop=page.cropbox
                preserved_pixels=False
                if (source_pdf is not None and
                        (row['policy']=='preserved_figure' or row['role'] in {'abandon','fallback_line'})
                        and not row['inputs'] and row['source_box']):
                    # Rotated metadata may use glyph coordinates that are not
                    # directly comparable with extraction boxes. Demand exact
                    # pixel preservation of that source region instead.
                    x0,y0,x1,y1=row['source_box']
                    clip=fitz.Rect(x0-crop.x0-2,height-y1-crop.y0-2,x1-crop.x0+2,height-y0-crop.y0+2)
                    original=source_pdf[row['source_page']-1].get_pixmap(clip=clip,colorspace=fitz.csGRAY,alpha=False)
                    rendered=page.get_pixmap(clip=clip,colorspace=fitz.csGRAY,alpha=False)
                    preserved_pixels=pixels_preserved(original,rendered)
                for glyph in ([] if preserved_pixels else glyphs):
                    x0,y0,x1,y1=glyph['box'];x=(x0+x1)/2-crop.x0;y=height-(y0+y1)/2-crop.y0
                    # PDF extraction boxes are font ascenders, while the IL
                    # boxes are advance-height boxes. The baseline offset can
                    # exceed two points for small chart labels, even when the
                    # glyph's actual x/y position is unchanged.
                    tolerance=max(4.,abs(y1-y0)*.5)
                    cid_glyph=bool(re.fullmatch(r'\(cid:\d+\)',glyph['text']))
                    for c in ('\ufffd' if cid_glyph else canonical(glyph['text'])):
                        needed+=1;options=[]
                        if cid_glyph:tolerance=max(tolerance,7.)
                        if cid_glyph:
                            # An embedded math font may expose its CID as a
                            # raw control/Latin code in the exported PDF, not
                            # U+FFFD. Match that exact CID at its planned
                            # position before treating the glyph as missing.
                            code=int(glyph['text'][5:-1]);raw=chr(code) if code<=0x10ffff else None
                            cid_tolerance=max(tolerance,10.)
                            if raw is not None:
                                for gx in range(math.floor((x-cid_tolerance)/16),math.floor((x+cid_tolerance)/16)+1):
                                    for gy in range(math.floor((y-cid_tolerance)/16),math.floor((y+cid_tolerance)/16)+1):
                                        for item in raw_pools[page_index].get((gx,gy,raw),[]):
                                            if item[0] not in used_cids[page_index] and abs(item[2]-x)<=2 and abs(item[3]-y)<=cid_tolerance:
                                                options.append(((item[2]-x)**2+(item[3]-y)**2,item[0]))
                            if options:
                                used_cids[page_index].add(min(options)[1]);continue
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
            preserved_references=sum(r['policy']=='preserved_reference' for r in self.rows),
            pixel_verified_index_pages=sorted(verified_index),issues=issues,
            scope='Analyzed source occurrences, replay, typeset text counts and per-glyph PDF positions; restored index pages require exact source pixels. Not OCR recall, reading order or semantic certification.')
        if save_report:save(self.folder/'region-coverage.json',report)
        return report


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
