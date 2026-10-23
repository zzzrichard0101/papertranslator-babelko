"""Actual BabelDOC layout/OCR/export with a loopback synthetic translator; not semantic evaluation."""
import argparse,json,os,re,threading,uuid,subprocess,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
import pymupdf as fitz
from babelko.pipeline import create,run
from babelko.storage import project,save,read,digest

WORDS={'Synthetic':'합성','research':'연구','study':'연구','Research':'연구','evidence':'근거','does':'','not':'않는다','replace':'대체','clinical':'임상','judgement':'판단','The':'이','included':'포함','participants':'참가자','Group':'집단','Participants':'참가자','Control':'대조군','Treatment':'치료군','Table':'표','Results':'결과','were':'','measured':'측정','after':'이후','training':'학습','Original':'원문','layout':'배치'}

def converted(text):return re.sub(r'[A-Za-z]+',lambda m:WORDS.get(m[0],m[0]),text)


def main(mode='qwen',experimental=False,diverse=False):
    p=project();work=p/'test_vault'/('integration-'+mode+'-'+uuid.uuid4().hex[:8]);work.mkdir(parents=True)
    home=work/'home';home.mkdir();prepared=Path(os.environ['LOCALAPPDATA'])/'PaperTranslatorBabelKO/assets'
    if prepared.is_dir():
        command="New-Item -ItemType Junction -Path '"+str(home/'assets').replace("'","''")+"' -Target '"+str(prepared).replace("'","''")+"' | Out-Null"
        subprocess.run(['powershell','-NoProfile','-Command',command],check=True,capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
    os.environ['BABELKO_HOME']=str(home)
    registry=work/'models.json';save(registry,dict(runtime_dir='synthetic',runtime_release='synthetic',models=dict(qwen38=dict(id='synthetic-qwen',adapter='qwen',path='unused',sha256=uuid.uuid4().hex),hy30b=dict(id='synthetic-hy',adapter='hy',path='unused',sha256=uuid.uuid4().hex))))
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
        if experimental:page.insert_text((45,670),'Research evidence--based practice (EBP).',fontsize=11)
        scan=page.get_pixmap(matrix=fitz.Matrix(2,2),alpha=False)
        raster=doc.new_page(width=600,height=800);raster.insert_image(raster.rect,pixmap=scan)
        refs=doc.new_page(width=600,height=800)
        refs.insert_text((45,75),'References',fontsize=18)
        refs.insert_text((45,120),'Smith, J. (2020). A study of art. Oxford, NY: Example Press.',fontsize=9)
        refs.insert_text((45,150),'Jones, A. (2021). Clinical evidence. Journal of Research, 12(2), 30-42.',fontsize=9)
        if diverse:
            landscape=doc.new_page(width=800,height=600)
            for x in [45,420]:landscape.insert_textbox(fitz.Rect(x,100,x+320,260),'Research evidence does not replace clinical judgement. The study included 24 participants.',fontsize=11)
            # Native text rotated in the source, normalized for analysis then
            # restored by the app. Spatial validation must use PDF coordinates.
            rotated=doc.new_page(width=600,height=800)
            rotated.insert_textbox(fitz.Rect(50,110,540,240),'Research evidence does not replace clinical judgement. The study included 24 participants.',fontsize=11)
            rotated.set_rotation(90)
        doc.save(source)
    source_sha=digest(source);calls=[];bad=[False];repair_faults=[0]
    class Server(BaseHTTPRequestHandler):
        def log_message(self,*a):pass
        def do_POST(self):
            payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])));calls.append(payload)
            inputs=next((m['content'].rsplit('## Here is the input:',1)[1].strip() for m in payload['messages'] if '## Here is the input:' in m['content']),None)
            if inputs:
                content=[dict(id=x['id'],output=converted(x['input'])) for x in json.loads(inputs)]
                if not bad[0]:content=[];bad[0]=True
                text=json.dumps(content,ensure_ascii=False)
            elif payload['messages'][0]['content'].startswith('Review EACH'):
                data=json.loads(payload['messages'][-1]['content'])
                text=json.dumps([dict(id=item['id'],decision='keep',patches=[]) for item in data])
            elif payload['messages'][0]['content'].startswith('Act as a skeptical bilingual'):
                data=json.loads(payload['messages'][1]['content'])
                text=json.dumps([dict(id=item['id'],verdict='faithful',evidence=[x['id'] for x in data['UNITS'] if x['side']!=item['side'] and x.get('record_id')==item.get('record_id')],reason='') for item in data['UNITS'] if item['id'] in data['CHECK_IDS']],ensure_ascii=False)
                if payload['response_format']['json_schema']['schema']['items']['type']=='array':
                    text=json.dumps([[v[k] for k in ['id','verdict','evidence','reason']] for v in json.loads(text)])
            elif payload['messages'][0]['content'].startswith('Translate the following TARGET'):
                original=payload['messages'][0]['content'].rsplit('\n\n',1)[1]
                text=converted(original)
                if not bad[0] and '24' in original:text=text.replace('24','42');bad[0]=True
            elif payload['messages'][0]['content'].startswith('Translate ONLY the value of SOURCE'):
                text=converted(json.loads(payload['messages'][1]['content'])['SOURCE'])
                if mode=='hybrid' and '24' in text and repair_faults[0]<3:
                    repair_faults[0]+=1;text=text.replace('24','42')
            else:
                original=next((m['content'].rsplit('Now translate the following text:',1)[1].strip() for m in payload['messages'] if 'Now translate the following text:' in m['content']),None)
                if original is None:original=next((m['content'].rsplit('Input:\n\n',1)[1] for m in payload['messages'] if 'Input:\n\n' in m['content']),'Hello')
                text=converted(original)
            value=dict(id='synthetic',object='chat.completion',created=0,model='synthetic',choices=[dict(index=0,message=dict(role='assistant',content=text),finish_reason='stop')],usage=dict(prompt_tokens=10,completion_tokens=10,total_tokens=20))
            data=json.dumps(value,ensure_ascii=False).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    server=ThreadingHTTPServer(('127.0.0.1',0),Server);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    events=[]
    class Engine:
        def __init__(self,*a,snapshot=None,**kw):self.model=snapshot['model'];self.url=f'http://127.0.0.1:{server.server_port}/v1';self.key='synthetic'
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def start(self,*a):events.append(('start',self.model['id']))
        def close(self):events.append(('close',self.model['id']))
    try:
        with patch('babelko.engine.LocalEngine',Engine):
            folder=create(source,p/'test_vault',mode=mode,experimental_pipeline=experimental);result=run(folder)
            assert result['status']=='completed',result
            out=Path(result['output']);quality=read(out/'Quality.json')
            if experimental:
                assert quality['region_coverage']['status']=='passed' and quality['region_coverage']['checked_regions']>10
                assert 'EBP' in quality['document_context']['entries']
            assert quality['ocr_source_pages']==[2]
            assert quality['references']['policy']=='original' and len(quality['references']['paragraphs'])>=2
            if mode=='qwen':assert quality['retries']>=1
            else:
                assert quality['hybrid']['reviewed']>0 and quality['hybrid']['retranslated']>=1
                assert repair_faults[0]==3 and not quality['unresolved_translation_failures']
                assert read(folder/'pending-review.json')['pending']==[]
                assert quality['meaning_assurance']['status']=='passed' and quality['meaning_assurance']['audited_units']>0
                assert events[:3]==[('start','synthetic-hy'),('close','synthetic-hy'),('start','synthetic-qwen')],events
            assert digest(source)==source_sha==digest(out/'Original.pdf')
            # Force a worker-style resume, bypassing only the completed-job
            # shortcut. Cached native IL must retain text/geometry and proofs,
            # and a fully cached document must load neither local model.
            before_calls=len(calls);before_events=len(events);cold_performance=read(folder/'performance.json')
            with fitz.open(out/'Korean.pdf') as before_pdf:
                before_words=[p.get_text('words') for p in before_pdf]
                before_pixels=[p.get_pixmap(alpha=False).samples for p in before_pdf]
            state=read(folder/'state.json');state.update(status='cancelled');save(folder/'state.json',state)
            started=time.perf_counter();resumed=run(folder);resume_seconds=time.perf_counter()-started
            assert resumed['status']=='completed' and read(folder/'layout-cache-report.json')['status']=='hit'
            assert len(calls)==before_calls and not any(e[0]=='start' for e in events[before_events:]),events[before_events:]
            with fitz.open(Path(resumed['output'])/'Korean.pdf') as reread:
                assert [p.get_text('words') for p in reread]==before_words
                assert [p.get_pixmap(alpha=False).samples for p in reread]==before_pixels
            with fitz.open(out/'Korean.pdf') as ko,fitz.open(out/'Bilingual.pdf') as dual:
                assert len(ko)==len(dual)==(5 if diverse else 3) and all(any('가'<=c<='힣' for c in page.get_text()) for page in list(ko)[:2])
                if diverse:assert ko[4].rotation==90 and ko[3].rect.width==800
                for page in list(ko)[:2]:
                    assert all(term in page.get_text() for term in ['집단','대조군','치료군']) and 'Hello' not in page.get_text()
                    assert page.get_text().split().count('12')==2
                assert 'A study of art.' in ko[2].get_text() and 'Clinical evidence.' in ko[2].get_text()
                with fitz.open(source) as original:
                    expected=original[2].get_text('words');actual=ko[2].get_text('words')
                    assert [w[4] for w in expected]==[w[4] for w in actual]
                    assert max(abs(a[n]-b[n]) for a,b in zip(expected,actual) for n in range(4))<.01
            assert all('A study of art.' not in m['content'] and 'Clinical evidence.' not in m['content'] for call in calls for m in call['messages'])
            source_batches=[json.loads(m['content'].rsplit('## Here is the input:',1)[1]) for call in calls for m in call['messages'] if '## Here is the input:' in m['content']]
            body_inputs=[item['input'] for batch in source_batches for item in batch if 'Research evidence' in item['input']]
            if mode=='qwen':assert body_inputs and all('clinical judgement.' in text for text in body_inputs),body_inputs
            else:
                records=[read(path) for path in (folder/'hybrid').glob('*.json')]
                assert all(not record.get('final_error') and record.get('final') for record in records)
                assert any(record.get('draft_errors') for record in records)
            before=len(calls);again=run(folder);assert again['output']==resumed['output'] and len(calls)==before
            loss_rejected=None
            cell_move_rejected=None
            if mode=='hybrid':
                # Inject an exporter that loses every translated glyph. File
                # existence/page counts alone must never count as completion.
                def lost_export(input_path,destination):
                    with fitz.open(input_path) as original,fitz.open() as blank:
                        for page in original:
                            placeholder=blank.new_page(width=page.rect.width,height=page.rect.height)
                            placeholder.insert_text((30,40),'Exporter fault: translated prose lost.')
                        blank.save(destination)
                broken=create(source,p/'test_vault',mode=mode,experimental_pipeline=experimental)
                with patch('babelko.pdf_preservation.optimize',lost_export):run(broken)
                failed=read(broken/'state.json');report=read(Path(failed['output'])/'Quality.json')
                assert failed['status']=='partial' and report['rendered_prose']['status']=='failed'
                assert digest(source)==digest(Path(failed['output'])/'Original.pdf')
                loss_rejected=True
                if experimental:
                    # Keep every word/number but move a short table cell. The
                    # previous prose-only gate cannot detect this spatial fault.
                    from babelko.pdf_preservation import optimize as real_optimize
                    def moved_cell(input_path,destination):
                        real_optimize(input_path,destination)
                        with fitz.open(destination) as pdf:
                            cell=next(w for w in pdf[0].get_text('words') if w[4]=='12')
                            pdf[0].add_redact_annot(fitz.Rect(*cell[:4]),fill=(1,1,1))
                            pdf[0].apply_redactions(images=0,graphics=0)
                            pdf[0].insert_text((cell[0]+100,cell[3]-2),'12',fontsize=11)
                            pdf.saveIncr()
                    broken=create(source,p/'test_vault',mode=mode,experimental_pipeline=True)
                    with patch('babelko.pdf_preservation.optimize',moved_cell):run(broken)
                    failed=read(broken/'state.json');report=read(Path(failed['output'])/'Quality.json')
                    assert failed['status']=='partial'
                    assert report['rendered_prose']['status']=='passed'
                    assert report['region_coverage']['status']=='failed'
                    assert any('pdf_glyph_missing_or_moved' in v.get('codes',[]) for v in report['region_coverage']['issues'])
                    cell_move_rejected=True
            save(work/'result.json',dict(status='passed',output=str(out),source_hash_equal=True,ocr_scan_only=True,invalid_candidate_repaired=True,replay_without_calls=True,export_loss_rejected=loss_rejected,cell_move_rejected=cell_move_rejected,local_model_calls=False,
                native_cache_resume=dict(seconds=round(resume_seconds,3),cache_hit=True,model_requests=0,model_loads=0,text_and_geometry_equal=True,rendered_pixels_equal=True),cold_performance=cold_performance))
            print(json.dumps(read(work/'result.json'),ensure_ascii=False))
    finally:server.shutdown();server.server_close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--mode',choices=['qwen','hybrid'],default='qwen');parser.add_argument('--experimental-pipeline',action='store_true');parser.add_argument('--diverse',action='store_true');args=parser.parse_args();main(args.mode,args.experimental_pipeline,args.diverse)
