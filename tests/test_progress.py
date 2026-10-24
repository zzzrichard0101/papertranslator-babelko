from unittest.mock import patch
import pytest
from babelko.progress import track_translation_pages,translate
from babelko.upstream import prepare


class Monitor:
    def __init__(self,*a,**kw):self.callback=kw['progress_change_callback'];self.cancelled=False
    def cancel(self):self.cancelled=True


def test_return_value_completes_even_without_a_finish_event():
    prepare();events=[];details=[]
    def process(monitor,config):monitor.callback(type='progress_update',stage='Save PDF',stage_current=2,stage_total=3,overall_progress=100);return 'actual-result'
    with patch('babeldoc.format.pdf.high_level.do_translate',process),patch('babeldoc.format.pdf.high_level.get_translation_stage',lambda _:[]),patch('babeldoc.progress_monitor.ProgressMonitor',Monitor):
        assert translate(object(),lambda *v:events.append(v),on_event=details.append)=='actual-result'
    assert events==[('Save PDF',100)]
    assert details[0]['stage_current']==2 and details[0]['stage_total']==3


def test_engine_exception_is_propagated_instead_of_waiting_forever():
    prepare()
    def process(*a):raise ValueError('synthetic failure')
    with patch('babeldoc.format.pdf.high_level.do_translate',process),patch('babeldoc.format.pdf.high_level.get_translation_stage',lambda _:[]),patch('babeldoc.progress_monitor.ProgressMonitor',Monitor):
        with pytest.raises(ValueError,match='synthetic failure'):translate(object(),lambda *a:None)



def test_cancellation_stops_the_owned_engine_and_propagates():
    import time,asyncio
    prepare();aborts=[]
    def process(monitor,config):
        while not monitor.cancelled:time.sleep(.01)
        raise asyncio.CancelledError()
    with patch('babeldoc.format.pdf.high_level.do_translate',process),patch('babeldoc.format.pdf.high_level.get_translation_stage',lambda _:[]),patch('babeldoc.progress_monitor.ProgressMonitor',Monitor):
        with pytest.raises(asyncio.CancelledError):translate(object(),lambda *a:None,lambda:True,lambda:aborts.append(True))
    assert aborts==[True]


def test_native_translation_batch_reports_real_source_pages_and_restores_upstream():
    from types import SimpleNamespace
    from babeldoc.format.pdf.document_il.midend.il_translator_llm_only import ILTranslatorLLMOnly
    pages=[]
    def original(self,batch):return 'translated'
    batch=SimpleNamespace(pages=[SimpleNamespace(page_number=2),SimpleNamespace(page_number=3),SimpleNamespace(page_number=2)])
    with patch.object(ILTranslatorLLMOnly,'translate_paragraph',original):
        with track_translation_pages(lambda event,current:pages.append((event,current))):
            assert ILTranslatorLLMOnly.translate_paragraph(object(),batch)=='translated'
        assert ILTranslatorLLMOnly.translate_paragraph is original
    assert pages==[('start',(3,4)),('finish',(3,4))]


def test_native_translation_batch_clears_active_pages_after_failure():
    from types import SimpleNamespace
    from babeldoc.format.pdf.document_il.midend.il_translator_llm_only import ILTranslatorLLMOnly
    events=[]
    def fails(self,batch):raise RuntimeError('batch failed')
    batch=SimpleNamespace(pages=[SimpleNamespace(page_number=4)])
    with patch.object(ILTranslatorLLMOnly,'translate_paragraph',fails):
        with track_translation_pages(lambda event,pages:events.append((event,pages))):
            with pytest.raises(RuntimeError,match='batch failed'):
                ILTranslatorLLMOnly.translate_paragraph(object(),batch)
    assert events==[('start',(5,)),('finish',(5,))]
