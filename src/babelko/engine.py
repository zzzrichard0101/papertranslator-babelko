"""Read-only reuse of installed local models; separate process and app data."""
import ctypes,json,os,secrets,socket,subprocess,time
from ctypes import wintypes
from pathlib import Path
import httpx,psutil
from .storage import root,read,digest

class OwnedJob:
    def __init__(self):
        class BASIC(ctypes.Structure):
            _fields_ = [('time1', ctypes.c_int64), ('time2', ctypes.c_int64), ('flags', wintypes.DWORD),
                        ('min', ctypes.c_size_t), ('max', ctypes.c_size_t), ('active', wintypes.DWORD),
                        ('affinity', ctypes.c_size_t), ('priority', wintypes.DWORD), ('scheduling', wintypes.DWORD)]
        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in ['r', 'w', 'o', 'rb', 'wb', 'ob']]
        class EXT(ctypes.Structure):
            _fields_ = [('basic', BASIC), ('io', IO), ('process', ctypes.c_size_t), ('job', ctypes.c_size_t),
                        ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.kernel.CreateJobObjectW.restype = wintypes.HANDLE
        self.kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        self.kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.kernel.CreateJobObjectW(None, None)
        info = EXT(); info.basic.flags = 0x2000  # KILL_ON_JOB_CLOSE
        if not self.handle or not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            self.close(); raise ctypes.WinError(ctypes.get_last_error())

    def assign(self, process):
        if not self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if getattr(self, 'handle', None):
            self.kernel.CloseHandle(self.handle); self.handle = None


def registry():
    default=root()/'local_models.json'
    if not default.exists():default=Path(os.environ['LOCALAPPDATA'])/'PaperTranslator/model_registry.json'
    return read(Path(os.environ.get('BABELKO_MODEL_REGISTRY',default)))

def models():return {k:v for k,v in registry().get('models',{}).items() if k in {'qwen38','hy30b','hy7b'}}


class LocalEngine:
    def __init__(self,folder,key='qwen38',cancel=lambda:False,snapshot=None):
        self.folder=Path(folder);self.cancel=cancel;self.registry=snapshot or registry();self.model=dict(snapshot['model'] if snapshot else models()[key]);self.process=None;self.job=None;self.log=None
        self.key=secrets.token_urlsafe(32)
    def capacity_args(self):
        slots=self.registry.get('review_slots',1)
        if type(slots) is not int or slots not in (1,2):raise ValueError('로컬 검수 슬롯 설정 오류')
        # llama.cpp's context size is TOTAL across slots. Preserve 8192 for
        # EACH request; neither quantize KV nor halve context to gain speed.
        return ['-c',str(8192*slots),'-np',str(slots)]
    def __enter__(self):return self
    def start(self,progress=print):
        if any((p.info['name'] or '').lower()=='llama-server.exe' for p in psutil.process_iter(['name'])):
            raise RuntimeError('다른 로컬 번역 엔진이 실행 중입니다. 해당 작업이 끝난 뒤 시작하세요.')
        path=Path(self.model['path']);progress('로컬 모델 무결성 검사')
        if digest(path)!=self.model['sha256']:raise RuntimeError('로컬 모델 SHA256 불일치')
        exe=next(Path(self.registry['runtime_dir']).rglob('llama-server.exe'))
        with socket.socket() as s:s.bind(('127.0.0.1',0));self.port=s.getsockname()[1]
        self.url=f'http://127.0.0.1:{self.port}/v1'
        opts=self.model.get('options',{})
        args=[str(exe),'-m',str(path),'--host','127.0.0.1','--port',str(self.port),'--api-key',self.key,
              '-ngl','99',*self.capacity_args(),'-t','12','-ctk','f16','-ctv','f16','-fa','auto',
              '--no-webui','--jinja','--no-context-shift','--offline']
        if 'enable_thinking' in opts:args+=['--chat-template-kwargs',json.dumps(dict(enable_thinking=opts['enable_thinking']))]
        if self.registry.get('mtp') and self.registry.get('runtime_release')=='b11718' and self.model.get('sha256')=='f5f1dd8920d417aac2718b0bda3403da274301efdd6760b4f0f4b864ff2ad57d':
            args+=['--spec-type','draft-mtp','--spec-draft-n-max','3']
        self.log=(self.folder/('engine-'+self.model.get('key','local')+'.log')).open('a',encoding='utf-8');self.job=OwnedJob()
        self.process=subprocess.Popen(args,cwd=exe.parent,stdout=self.log,stderr=self.log,creationflags=subprocess.CREATE_NO_WINDOW)
        try:self.job.assign(self.process)
        except BaseException:self.process.terminate();self.close();raise
        with httpx.Client(trust_env=False,timeout=2) as client:
            start=time.monotonic()
            while time.monotonic()-start<180:
                if self.cancel():raise InterruptedError('취소됨')
                if self.process.poll() is not None:raise RuntimeError('로컬 엔진 시작 실패: 작업 폴더의 engine-*.log 확인')
                try:
                    if client.get(self.url.removesuffix('/v1')+'/health').status_code==200:return self
                except httpx.HTTPError:pass
                time.sleep(.3)
        raise RuntimeError('로컬 엔진 적재 시간 초과')
    def close(self):
        if self.job:self.job.close();self.job=None
        if self.process and self.process.poll() is None:self.process.wait(timeout=15)
        if self.log:self.log.close();self.log=None
    def __exit__(self,*args):self.close()
