from unittest.mock import patch
import pytest
from babelko.progress import translate
from babelko.upstream import prepare


class Monitor:
    def __init__(self,*a,**kw):self.callback=kw['progress_change_callback'];self.cancelled=False
    def cancel(self):self.cancelled=True


def test_return_value_completes_even_without_a_finish_event():
    prepare();events=[]
    def process(monitor,config):monitor.callback(type='progress_update',stage='Save PDF',overall_progress=100);return 'actual-result'
    with patch('babeldoc.format.pdf.high_level.do_translate',process),patch('babeldoc.format.pdf.high_level.get_translation_stage',lambda _:[]),patch('babeldoc.progress_monitor.ProgressMonitor',Monitor):
        assert translate(object(),lambda *v:events.append(v))=='actual-result'
    assert events==[('Save PDF',100)]


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
