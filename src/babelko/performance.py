"""Low-overhead local measurements; never trade a correctness check for time."""
import collections,re,time,threading
from contextlib import contextmanager
from .storage import save


class Performance:
    def __init__(self,folder):
        self.folder=folder;self.started=time.perf_counter();self.current=None;self.changed=self.started
        self.times=collections.defaultdict(float);self.calls=collections.Counter();self.last_save=0.;self.lock=threading.RLock()

    def stage(self,message):
        name=re.sub(r'\d+(?:\.\d+)?','#',message).split(':',1)[0]
        with self.lock:
            now=time.perf_counter()
            if name!=self.current:
                if self.current:self.times['stage.'+self.current]+=now-self.changed
                self.current=name;self.changed=now
            if now-self.last_save>=5:self.flush()

    def add(self,name,seconds=0,count=1):
        with self.lock:self.times[name]+=seconds;self.calls[name]+=count

    @contextmanager
    def measure(self,name):
        start=time.perf_counter()
        try:yield
        finally:self.add(name,time.perf_counter()-start)

    def snapshot(self):
        with self.lock:
            now=time.perf_counter();times=dict(self.times)
            if self.current:times['stage.'+self.current]=times.get('stage.'+self.current,0)+now-self.changed
            return dict(elapsed_seconds=round(now-self.started,3),seconds={k:round(v,3) for k,v in times.items()},counts=dict(self.calls),
                scope='Per-run observed wall time. Stage and measured component times may overlap; do not sum them.')

    def flush(self):
        with self.lock:save(self.folder/'performance.json',self.snapshot());self.last_save=time.perf_counter()


class StateWriter:
    """Throttle progress only; phase changes, failures and completion are durable."""
    def __init__(self,path):self.path=path;self.last=0.;self.signature=None
    def write(self,state,force=False):
        now=time.monotonic();signature=(state.get('status'),state.get('error'))
        if force or signature!=self.signature or now-self.last>=.5 or state.get('progress')==100:
            save(self.path,state);self.last=now;self.signature=signature;return True
        return False
