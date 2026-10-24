"""Wait for actual engine completion; avoid the upstream async-callback finish race."""
from concurrent.futures import ThreadPoolExecutor,TimeoutError
from contextlib import contextmanager
from unittest.mock import patch
import threading
from .upstream import prepare


@contextmanager
def track_translation_pages(callback):
    """Observe active native translation batches without changing BabelDOC's source."""
    prepare()
    from babeldoc.format.pdf.document_il.midend.il_translator_llm_only import ILTranslatorLLMOnly

    original = ILTranslatorLLMOnly.translate_paragraph

    def tracked(self, batch, *args, **kwargs):
        pages = tuple(dict.fromkeys(
            page.page_number + 1 for page in batch.pages
            if isinstance(getattr(page, "page_number", None), int)
        ))
        if pages:
            callback("start", pages)
        try:
            return original(self, batch, *args, **kwargs)
        finally:
            if pages:
                callback("finish", pages)

    with patch.object(ILTranslatorLLMOnly, "translate_paragraph", tracked):
        yield


def translate(config,progress,cancel=lambda:False,abort=lambda:None,on_event=None):
    prepare()
    from babeldoc.format.pdf.high_level import do_translate,get_translation_stage
    from babeldoc.progress_monitor import ProgressMonitor
    def event(**value):
        if value.get('type','').startswith('progress'):
            if on_event:on_event(value)
            progress(value.get('stage','번역 중'),value.get('overall_progress',0))
    monitor=ProgressMonitor(get_translation_stage(config),progress_change_callback=event,
        finish_callback=lambda **value:None,cancel_event=threading.Event())
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(do_translate,monitor,config);aborted=False
        while True:
            if cancel() and not aborted:monitor.cancel();abort();aborted=True
            try:return future.result(timeout=.2)
            except TimeoutError:
                if future.done():return future.result()
