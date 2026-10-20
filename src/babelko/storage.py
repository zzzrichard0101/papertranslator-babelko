import hashlib,json,os,time,uuid
from pathlib import Path


def project():return Path(__file__).resolve().parents[2]
def root():
    path=Path(os.environ.get('BABELKO_HOME',Path(os.environ['LOCALAPPDATA'])/'PaperTranslatorBabelKO'))
    path.mkdir(parents=True,exist_ok=True);return path

def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with temp.open('w',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2,default=str);f.flush();os.fsync(f.fileno())
        # Windows readers (including the GUI's polling open) can briefly deny
        # replacement. Keep the complete old file until replacement succeeds;
        # never truncate the shared destination or retry permanent failures forever.
        deadline=time.monotonic()+2;delay=.01
        while True:
            try:os.replace(temp,path);break
            except OSError as exc:
                if getattr(exc,'winerror',None) not in {5,32,33} or time.monotonic()>=deadline:raise
                time.sleep(min(delay,max(0,deadline-time.monotonic())));delay=min(delay*2,.1)
    finally:
        temp.unlink(missing_ok=True)
def digest(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
