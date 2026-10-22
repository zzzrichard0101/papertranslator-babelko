"""Reproducible diverse corpus. Downloaded PDFs/results stay in test_vault.

Selected-page checks, not claims about every page or semantic certification.
"""
import argparse,concurrent.futures,json,os,subprocess,sys,shutil
from pathlib import Path
import pymupdf as fitz
from babelko.storage import project,save,read,digest

PUBLIC=[
 dict(key='acl',url='https://aclanthology.org/2020.acl-main.703.pdf',pages='1,4',kind='two-column NLP paper, tables, equations, footnotes'),
 dict(key='jmlr',url='https://www.jmlr.org/papers/volume18/16-365/16-365.pdf',pages='1,3',kind='single-column software paper, code and citations'),
 dict(key='nist',url='https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf',pages='6,28',kind='government report, prose and long table'),
 dict(key='nasa',url='https://www.nasa.gov/wp-content/uploads/static/apollo50th/pdf/A11_PressKit.pdf',pages='6',kind='historical photocopy scan'),
 dict(key='rfc',url='https://www.rfc-editor.org/rfc/rfc9000.pdf',pages='10,62',kind='protocol specification, normative conditions and packet fields'),
 dict(key='adam',url='https://arxiv.org/pdf/1412.6980v9',pages='2,3',kind='mathematical optimization paper, algorithms and equations'),
]


def prepare(base):
    import requests
    sources=base/'sources';sources.mkdir(parents=True,exist_ok=True)
    def fetch(case):
        path=sources/(case['key']+'.pdf')
        if not path.exists():
            response=requests.get(case['url'],timeout=120);response.raise_for_status()
            if not response.content.startswith(b'%PDF-'):raise ValueError('Not a PDF: '+case['key'])
            path.write_bytes(response.content)
        with fitz.open(path) as doc:count=len(doc)
        return dict(**case,source=str(path),sha256=digest(path),total_pages=count)
    # Independent read-only downloads; actual GPU translations remain serial.
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:cases=list(pool.map(fetch,PUBLIC))
    synthetic=sources/'controlled-layouts.pdf'
    if not synthetic.exists():
        with fitz.open() as doc:
            for columns in [1,2,3]:
                page=doc.new_page(width=600,height=800);page.insert_text((40,55),f'Controlled {columns} column study',fontsize=17)
                width=520/columns
                for c in range(columns):
                    for row in range(3):
                        text=('The response decreased, but the uncertainty increased. '
                              'Only participants with dry equipment were included. '
                              'No causal effect was established; the change may reflect selection.')
                        assert page.insert_textbox(fitz.Rect(40+c*width,100+row*190,30+(c+1)*width,270+row*190),text,fontsize=10)>0
                page.insert_text((40,740),'Footnote: the estimate is not a guarantee.',fontsize=8)
            page=doc.new_page(width=800,height=600)
            page.insert_text((40,60),'Landscape table and exact units',fontsize=17)
            for y in [100,140,180,220]:page.draw_line((40,y),(750,y))
            for x in [40,290,520,750]:page.draw_line((x,100),(x,220))
            for x,text in [(50,'Group'),(300,'Mass (mg)'),(530,'Change (%)')]:page.insert_text((x,125),text)
            for x,text in [(50,'Control'),(300,'0.25'),(530,'-2.5'),(50,'Treatment'),(300,'0.50'),(530,'+3.0')]:
                page.insert_text((x,165 if text in ['Control','0.25','-2.5'] else 205),text)
            page.insert_text((40,290),'A lower value does not imply a stronger effect.',fontsize=12)
            page=doc.new_page(width=600,height=800)
            page.insert_textbox(fitz.Rect(50,90,540,300),'A page boundary must not remove the condition: the estimate is valid only if the sensor remains dry.',fontsize=13)
            page.set_rotation(90)
            pix=doc[1].get_pixmap(matrix=fitz.Matrix(2,2),alpha=False)
            page=doc.new_page(width=600,height=800);page.insert_image(page.rect,pixmap=pix)
            doc.save(synthetic)
    cases.append(dict(key='controlled',source=str(synthetic),sha256=digest(synthetic),pages='',total_pages=6,
        kind='controlled 1/2/3 columns, landscape table, rotated page, raster/native mixed document',url=None))
    save(base/'manifest.json',dict(scope='selected pages, downloaded public documents plus authored controls; not exhaustive',cases=cases))
    print(json.dumps([dict(key=c['key'],pages=c['pages'],total_pages=c['total_pages']) for c in cases]))


def run(base,keys,recheck=False):
    from babelko.pipeline import create,PROTOCOL,OCR_REVISION
    home=base/'home';home.mkdir(parents=True,exist_ok=True)
    assets=Path(os.environ['LOCALAPPDATA'])/'PaperTranslatorBabelKO/assets'
    link=home/'assets'
    if not link.exists():
        # A junction reuses only prepared read-only assets, never user jobs.
        command="New-Item -ItemType Junction -Path '"+str(link).replace("'","''")+"' -Target '"+str(assets).replace("'","''")+"' | Out-Null"
        subprocess.run(['powershell','-NoProfile','-Command',command],check=True,capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
    os.environ['BABELKO_HOME']=str(home)
    output=base/'results';output.mkdir(exist_ok=True)
    results=base/'runs';results.mkdir(exist_ok=True)
    for case in read(base/'manifest.json')['cases']:
        if keys and case['key'] not in keys:continue
        record=results/(case['key']+'.json')
        assert digest(case['source'])==case['sha256']
        if record.exists():
            job=Path(read(record)['job'])
            state=read(job/'state.json')
            if state.get('protocol')!=PROTOCOL or state.get('ocr_revision')!=OCR_REVISION:
                previous=job;job=create(case['source'],output,case['pages'],mode='hybrid')
                if (previous/'hybrid').exists():shutil.copytree(previous/'hybrid',job/'hybrid')
                save(record,dict(key=case['key'],job=str(job),previous_job=str(previous),cache_scope='text-bound checkpoint reuse; functional recheck, not a fresh speed comparison'))
            if recheck:
                # Re-run the updated program with its own checkpoints; never
                # modify translations or PDFs. Prior outputs remain preserved.
                state=read(job/'state.json');state.update(status='queued',stage='Updated adapter functional recheck');save(job/'state.json',state)
        else:
            job=create(case['source'],output,case['pages'],mode='hybrid');save(record,dict(key=case['key'],job=str(job)))
        with (results/(case['key']+'.log')).open('a',encoding='utf-8') as log:
            p=subprocess.run([sys.executable,'-m','babelko.worker',str(job)],cwd=project(),env={**os.environ,'PYTHONIOENCODING':'utf-8'},stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        state=read(job/'state.json');save(record,dict(**{k:v for k,v in read(record).items() if k not in {'key','job','status','output','error','returncode'}},key=case['key'],job=str(job),status=state['status'],output=state.get('output'),error=state.get('error'),returncode=p.returncode))
        print(case['key'],state['status'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','run']);p.add_argument('--base',type=Path,default=project()/'test_vault/accuracy-diverse-20261021');p.add_argument('--case',action='append',default=[]);p.add_argument('--recheck',action='store_true');a=p.parse_args()
    a.base=a.base.resolve();a.base.mkdir(parents=True,exist_ok=True)
    prepare(a.base) if a.action=='prepare' else run(a.base,a.case,a.recheck)
