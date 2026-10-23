"""Explicit, unverified PDF preview from read-only translation checkpoints.

This separate exporter cannot run inference or change the normal completion
gate. Unsafe rich-text candidates fall back to the complete source fragment.
"""
import collections,datetime,hashlib,html,json,os,threading,time,uuid
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
import psutil
import pymupdf as fitz
from .storage import read,save,digest,root
from .hybrid import HybridTranslator,context_hints,split_source,literal,prepare_layout
from .translator import PLACEHOLDER
from .policy import PROTOCOL,OCR_REVISION


def structurally_safe(source,target):
    if not isinstance(target,str) or not target.strip():return False
    if collections.Counter(PLACEHOLDER.findall(source))!=collections.Counter(PLACEHOLDER.findall(target)):return False
    depth=0
    for token in PLACEHOLDER.findall(target):
        if token.startswith('<style'):depth+=1
        elif token=='</style>':
            depth-=1
            if depth<0:return False
    return depth==0


class PreviewTranslator(HybridTranslator):
    name='babelko-preview'
    def __init__(self,settings,rate_limiter,source_job,folder,cancel=lambda:False):
        # Initialize only the native base contract: no HTTP client/model engine.
        from pdf2zh_next.translator.base_translator import BaseTranslator
        BaseTranslator.__init__(self,settings,rate_limiter)
        self.model='checkpoint-preview';self.folder=folder;self.cancel=cancel;self.local=threading.local();self.visits=[]
        self.rows={};self.by_source=collections.defaultdict(list)
        self.source_repairs={}
        for path in (source_job/'hybrid').glob('*.json'):
            row=read(path)
            if path.stem!=row.get('key'):raise ValueError('미리보기 체크포인트 식별자 불일치')
            self.rows[row['key']]=row;self.by_source[(row['source'],row['label'])].append(row)

    def _request(self,*args,**kwargs):raise RuntimeError('확인용 PDF는 모델 호출을 허용하지 않습니다.')

    def unit(self,source,label,context,hints=None):
        if self.cancel():raise InterruptedError('확인용 PDF 생성 취소됨')
        parts=split_source(source)
        if len(parts)>1:return ' '.join(self.unit(p.strip(),label,context,hints) for p in parts)
        context=context_hints(context)
        key=hashlib.sha256(json.dumps([PROTOCOL,source,label,context,hints or {}],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        row=self.rows.get(key)
        original_source=getattr(self,'source_repairs',{}).get(source,{}).get('before',source)
        if row is None and original_source!=source:
            old=self.by_source.get((original_source,label),[])
            matching=[r for r in old if r.get('context','')==context]
            if len(matching)==1:row=matching[0]
        if row and (row['source'] not in {source,original_source} or row['label']!=label or row.get('context','')!=context):raise ValueError('미리보기 체크포인트 원문 불일치')
        if row is None:
            choices=self.by_source.get((source,label),[])
            exact=[r for r in choices if r.get('context','')==context]
            choices=exact or choices
            # Do not guess between conflicting contextual translations.
            if choices and len({r.get('final') or r.get('draft') for r in choices})==1:row=choices[0]
        target=source;selection='source_missing_checkpoint'
        if literal(source):selection='source_literal'
        elif row:
            selection='source_unsafe_candidate'
            for name in ['final','draft']:
                if structurally_safe(source,row.get(name)):
                    target=row[name];selection=name;break
        self.translate_cache_call_count+=bool(row)
        self.visits.append(dict(key=row['key'] if row else key,source=source,target=target,selection=selection,
            page_candidates=getattr(self.local,'pages',[])))
        return target


@contextmanager
def preview_layout(translator,input_pdf):
    from babeldoc.format.pdf.document_il.midend.il_translator_llm_only import ILTranslatorLLMOnly as Native
    from .source_flow import source_flow
    from .text_structure import prose_structure
    repairs={};scan_plans={};scan_sources={}
    class CachedLayout(Native):
        def translate(self,docs):
            prepare_layout(docs,translator.folder,repairs,input_pdf)
            from .scan_evidence import cached,plan,apply
            source_job=input_pdf.parent
            if (source_job/'Original.pdf').is_file():
                scan_plans.update(plan(docs,source_job,cached(source_job),translator.folder))
                scan_sources.update({key[1]:value for key,value in scan_plans.items()})
            result=super().translate(docs)
            apply(docs,scan_plans)
            return result
        def translate_paragraph(self,batch,*args,**kwargs):
            translator.local.pages=sorted({p.page_number+1 for p in batch.pages})
            try:return super().translate_paragraph(batch,*args,**kwargs)
            finally:translator.local.pages=[]
    with source_flow(translator.folder),prose_structure(repairs,scan_sources,translator.register_source_repair),patch('babeldoc.format.pdf.high_level.ILTranslatorLLMOnly',CachedLayout):yield


def export(job,output_parent=None,pages=''):
    from .upstream import prepare,assets
    from .offline import install
    from .pipeline import compose
    from .pdf_preservation import optimize
    from .progress import translate
    from .references import preserve
    from .figure_legends import preserve as preserve_figures
    from .validation import inspect_output,tracking_status
    job=Path(job).resolve();state=read(job/'state.json')
    if pages:
        from .pipeline import selected_pages
        with fitz.open(job/'Original.pdf') as source:chosen=selected_pages(pages,len(source))
        if not set(chosen)<=set(state['selected']):raise ValueError('기존 작업의 번역 범위 안에서 확인 쪽을 선택하세요.')
        state={**state,'pages':pages,'selected':chosen}
    if job.parent!=(root()/'jobs').resolve():raise ValueError('허용되지 않은 작업 경로')
    if state.get('protocol')!=PROTOCOL or state.get('ocr_revision')!=OCR_REVISION:raise ValueError('다른 처리 버전의 작업입니다.')
    if state.get('status') in {'preparing','translating','validating'}:raise RuntimeError('진행 중인 번역을 먼저 저장·중단하세요.')
    lock=root()/'worker.lock'
    with lock.open('x') as stream:
        json.dump(dict(pid=os.getpid(),created=psutil.Process().create_time()),stream);stream.flush();os.fsync(stream.fileno())
    work=job/('preview-'+uuid.uuid4().hex[:8]);work.mkdir();began=time.perf_counter()
    progress_state=dict(status='exporting',work=str(work),pid=os.getpid(),stage='저장된 입력 확인',progress=0)
    def progress(message,percent=None):
        progress_state.update(stage=message,elapsed_seconds=round(time.perf_counter()-began,2))
        if percent is not None:progress_state['progress']=percent
        save(job/'preview-state.json',progress_state)
    cancel=lambda:(work/'cancel').exists()
    try:
        progress('저장된 원문·OCR 입력 해시 확인',0)
        if digest(job/'Original.pdf')!=state['source_sha256'] or digest(job/'Input.pdf')!=state['input_sha256']:raise ValueError('저장된 입력 해시 불일치')
        input_pdf=job/'Input.pdf'
        if (job/'layout-input.json').is_file():
            from .scan_evidence import LAYOUT_REVISION
            layout=read(job/'layout-input.json')
            if layout.get('revision')==LAYOUT_REVISION:
                if layout.get('original_input_sha256')!=state['input_sha256'] or digest(job/'Layout-input.pdf')!=layout['sha256']:raise ValueError('복구된 조판 입력 해시 불일치')
                input_pdf=job/'Layout-input.pdf'
        prepare();assets(progress);install()
        from pdf2zh_next.config.model import SettingsModel
        from pdf2zh_next.config.translate_engine_model import OpenAISettings
        from pdf2zh_next.high_level import create_babeldoc_config
        from pdf2zh_next.translator.base_rate_limiter import BaseRateLimiter
        from babeldoc.format.pdf.high_level import init
        init();settings=SettingsModel(translate_engine_settings=OpenAISettings(openai_model='checkpoint-preview',openai_base_url='http://127.0.0.1:9/v1',openai_api_key='disabled'))
        settings.translation.lang_in='en';settings.translation.lang_out='ko';settings.translation.qps=100
        settings.translation.pool_max_workers=1;settings.translation.no_auto_extract_glossary=True;settings.translation.min_text_length=1
        settings.translation.output=str(work/'babel_output');settings.pdf.pages=state['pages'] or None
        settings.pdf.only_include_translated_page=True;settings.pdf.no_dual=True;settings.pdf.watermark_output_mode='no_watermark'
        settings.pdf.skip_scanned_detection=bool(state.get('ocr_pages'));settings.pdf.translate_table_text=False
        translator=PreviewTranslator(settings,BaseRateLimiter(),job,work,cancel)
        with patch('pdf2zh_next.high_level.get_translator',lambda _:translator),patch('pdf2zh_next.high_level.get_term_translator',lambda _:translator):
            config=create_babeldoc_config(settings,input_pdf)
        config.translator=translator;config.term_extraction_translator=translator;config.add_formula_placehold_hint=True
        config.working_dir=work/'intermediate';config.working_dir.mkdir();config._is_temp_dir=False
        with preserve(work),preserve_figures(work),preview_layout(translator,input_pdf):
            result=translate(config,progress,cancel)
        if result is None or not result.mono_pdf_path:raise RuntimeError('확인용 PDF 조판 결과가 없습니다.')
        output_parent=Path(output_parent or state['destination']);output_parent.mkdir(parents=True,exist_ok=True)
        out=output_parent/(state['title'][:80]+' - PREVIEW '+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'));out.mkdir()
        progress('확인용 한국어 PDF 저장',97);optimize(result.mono_pdf_path,out/'Korean-preview.pdf')
        restore={v['source_page']-1:v['restore_rotation'] for v in state.get('input_transformations',{}).get('pages',[]) if v['restore_rotation']}
        with fitz.open(out/'Korean-preview.pdf') as doc:
            for i,source_page in enumerate(state['selected']):
                if source_page in restore:doc[i].set_rotation(restore[source_page])
            metadata=doc.metadata;metadata.update(title=state['title']+' [UNVERIFIED PREVIEW]',subject='Checkpoint preview; unresolved translation errors remain.');doc.set_metadata(metadata);doc.saveIncr()
        progress('원문·번역 확인용 대조본 생성',98);compose(job/'Original.pdf',out/'Korean-preview.pdf',out/'Bilingual-preview.pdf',state['selected'])
        pending=read(job/'pending-review.json').get('pending',[]);visits=translator.visits
        for row in pending:
            r=translator.rows[row['key']];used=[v for v in visits if v['key']==row['key']]
            row.update(source=r['source'],candidate=r.get('final') or r.get('draft'),
                page_candidates=sorted({p for v in used for p in v['page_candidates']}),selections=sorted({v['selection'] for v in used}))
        save(out/'Unresolved.json',pending)
        report=dict(status='preview_unverified',semantic_accuracy='not_certified',source_sha256=state['source_sha256'],
            unresolved_count=len(pending),model_calls=0,choices=dict(collections.Counter(v['selection'] for v in visits)),
            checks=inspect_output(out/'Korean-preview.pdf',state['selected']),tracking=tracking_status(work/'intermediate/translate_tracking.json'),
            output=str(out),seconds=round(time.perf_counter()-began,2),units=visits)
        save(out/'Preview.json',report)
        rows=''.join('<details><summary>'+html.escape(str(i+1)+'. '+r['error']+' · 원문 쪽 후보 '+str(r['page_candidates']))+'</summary><h3>원문</h3><p>'+html.escape(r['source'])+'</p><h3>저장된 번역 후보</h3><p>'+html.escape(r.get('candidate') or '(없음)')+'</p></details>' for i,r in enumerate(pending))
        (out/'Issues.html').write_text('<!doctype html><meta charset="utf-8"><title>확인용 PDF · 미해결 오류</title><style>body{font-family:system-ui;max-width:1000px;margin:36px auto;line-height:1.65}details{border-top:1px solid #ccc;padding:14px}p{white-space:pre-wrap}</style><h1>검수 미완료 확인용 PDF</h1><p>원문·번역 대조본과 한국어 PDF를 먼저 확인하기 위한 내보내기입니다. 번역 오류 '+str(len(pending))+'개가 남아 있으며 정식 완료본이 아닙니다. 쪽 후보는 해당 문단을 포함한 번역 배치의 물리적 원문 쪽입니다.</p><p><a href="Bilingual-preview.pdf">영한 대조본</a> · <a href="Korean-preview.pdf">한국어 확인본</a></p>'+rows,encoding='utf-8')
        progress_state.update(status='preview_ready',output=str(out));progress('확인용 PDF 저장 완료',100)
        return report
    except BaseException as exc:
        progress_state.update(status='failed',error=str(exc));progress('확인용 PDF 생성 실패');raise
    finally:lock.unlink(missing_ok=True)
