"""Wait for actual engine completion; avoid the upstream async-callback finish race."""
from concurrent.futures import ThreadPoolExecutor,TimeoutError
import threading
from .upstream import prepare


def translate(config,progress,cancel=lambda:False,abort=lambda:None):
    prepare()
    from babeldoc.format.pdf.high_level import do_translate,get_translation_stage
    from babeldoc.progress_monitor import ProgressMonitor
    def event(**value):
        if value.get('type','').startswith('progress'):
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
