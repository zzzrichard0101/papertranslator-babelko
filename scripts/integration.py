"""Actual BabelDOC layout/OCR/export with a loopback synthetic translator; not semantic evaluation."""
import json,os,re,threading,uuid
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
import pymupdf as fitz
from babelko.pipeline import create,run
from babelko.storage import project,save,read,digest

WORDS={'Synthetic':'합성','research':'연구','study':'연구','Research':'연구','evidence':'근거','does':'','not':'않는다','replace':'대체','clinical':'임상','judgement':'판단','The':'이','included':'포함','participants':'참가자','Group':'집단','Participants':'참가자','Control':'대조군','Treatment':'치료군','Table':'표','Results':'결과','were':'','measured':'측정','after':'이후','training':'학습','Original':'원문','layout':'배치'}

def converted(text):return re.sub(r'[A-Za-z]+',lambda m:WORDS.get(m[0],m[0]),text)


def main():
    p=project();work=p/'work/integration';work.mkdir(exist_ok=True)
    registry=work/'models.json';save(registry,dict(runtime_dir='synthetic',runtime_release='synthetic',models=dict(qwen38=dict(id='synthetic',adapter='qwen',path='unused',sha256=uuid.uuid4().hex))))
    os.environ['BABELKO_MODEL_REGISTRY']=str(registry)
    source=work/'Synthetic two column and scanned table.pdf'
    with fitz.open() as doc:
        page=doc.new_page(width=600,height=800);page.insert_text((50,70),'Synthetic research study',fontsize=18)
        for x in [45,315]:
            for y in [130,260,390]:page.insert_textbox(fitz.Rect(x,y,x+240,y+100),'Research evidence does not replace clinical judgement. The study included 24 participants.',fontsize=11)
        page.insert_text((45,540),'Table 1. Participants',fontsize=11)
        for y in [550,575,600,625]:page.draw_line((45,y),(555,y))
        page.insert_text((55,568),'Group');page.insert_text((350,568),'Participants')
        page.insert_text((55,593),'Control');page.insert_text((350,593),'12')
        page.insert_text((55,618),'Treatment');page.insert_text((350,618),'12')
        scan=page.get_pixmap(matrix=fitz.Matrix(2,2),alpha=False)
        raster=doc.new_page(width=600,height=800);raster.insert_image(raster.rect,pixmap=scan)
        doc.save(source)
    source_sha=digest(source);calls=[];bad=[False]
    class Server(BaseHTTPRequestHandler):
        def log_message(self,*a):pass
        def do_POST(self):
            payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])));calls.append(payload)
            inputs=next((m['content'].rsplit('## Here is the input:',1)[1].strip() for m in payload['messages'] if '## Here is the input:' in m['content']),None)
            if inputs:
                content=[dict(id=x['id'],output=converted(x['input'])) for x in json.loads(inputs)]
                if not bad[0]:content=[];bad[0]=True
                text=json.dumps(content,ensure_ascii=False)
            else:
                original=next((m['content'].rsplit('Now translate the following text:',1)[1].strip() for m in payload['messages'] if 'Now translate the following text:' in m['content']),None)
                if original is None:original=next((m['content'].rsplit('Input:\n\n',1)[1] for m in payload['messages'] if 'Input:\n\n' in m['content']),'Hello')
                text=converted(original)
            value=dict(id='synthetic',object='chat.completion',created=0,model='synthetic',choices=[dict(index=0,message=dict(role='assistant',content=text),finish_reason='stop')],usage=dict(prompt_tokens=10,completion_tokens=10,total_tokens=20))
            data=json.dumps(value,ensure_ascii=False).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    server=ThreadingHTTPServer(('127.0.0.1',0),Server);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    class Engine:
        def __init__(self,*a,snapshot=None,**kw):self.model=snapshot['model'];self.url=f'http://127.0.0.1:{server.server_port}/v1';self.key='synthetic'
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def start(self,*a):pass
        def close(self):pass
    try:
        with patch('babelko.engine.LocalEngine',Engine):
            folder=create(source,p/'test_vault');result=run(folder)
            assert result['status']=='completed',result
            out=Path(result['output']);quality=read(out/'Quality.json')
            assert quality['ocr_source_pages']==[2] and quality['retries']>=1
            assert digest(source)==source_sha==digest(out/'Original.pdf')
            with fitz.open(out/'Korean.pdf') as ko,fitz.open(out/'Bilingual.pdf') as dual:
                assert len(ko)==len(dual)==2 and all(any('가'<=c<='힣' for c in page.get_text()) for page in ko)
                for page in ko:
                    assert all(term in page.get_text() for term in ['집단','대조군','치료군']) and 'Hello' not in page.get_text()
                    assert page.get_text().split().count('12')==2
            source_batches=[json.loads(m['content'].rsplit('## Here is the input:',1)[1]) for call in calls for m in call['messages'] if '## Here is the input:' in m['content']]
            body_inputs=[item['input'] for batch in source_batches for item in batch if 'Research evidence' in item['input']]
            assert body_inputs and all('clinical judgement.' in text for text in body_inputs),body_inputs
            before=len(calls);again=run(folder);assert again['output']==result['output'] and len(calls)==before
            save(work/'result.json',dict(status='passed',output=str(out),source_hash_equal=True,ocr_scan_only=True,invalid_batch_retried=True,replay_without_calls=True,local_model_calls=False))
            print(json.dumps(read(work/'result.json'),ensure_ascii=False))
    finally:server.shutdown();server.server_close()


if __name__=='__main__':main()
