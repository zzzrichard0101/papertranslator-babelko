import hashlib,json,os,uuid
from pathlib import Path


def project():return Path(__file__).resolve().parents[2]
def root():
    path=Path(os.environ.get('BABELKO_HOME',Path(os.environ['LOCALAPPDATA'])/'PaperTranslatorBabelKO'))
    path.mkdir(parents=True,exist_ok=True);return path

def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    with temp.open('w',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2,default=str);f.flush();os.fsync(f.fileno())
    os.replace(temp,path)
def digest(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
