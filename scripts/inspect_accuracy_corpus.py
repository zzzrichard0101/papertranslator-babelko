"""Read-only, post-export QA of every available diverse-corpus result."""
import argparse,html,json,math,os,subprocess
from pathlib import Path
from urllib.parse import quote
import pymupdf as fitz
from PIL import Image,ImageOps,ImageDraw
from babelko.storage import project,read,save,digest


def inspect(base,meaning_results=()):
    poppler=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin/pdftoppm.exe'
    rows=[];sections=[]
    def link(p):return quote(os.path.relpath(p,base).replace('\\','/'),safe='/')
    for case in read(base/'manifest.json')['cases']:
        marker=base/'runs'/(case['key']+'.json')
        if not marker.exists():rows.append(dict(key=case['key'],status='not_run'));continue
        run=read(marker);job=Path(run['job']);state=read(job/'state.json')
        row=dict(key=case['key'],status=state['status'],selected_pages=case['pages'],kind=case['kind'],error=state.get('error'))
        if state.get('output'):
            out=Path(state['output']);quality=read(out/'Quality.json');dest=base/'assessment'/case['key'];dest.mkdir(parents=True,exist_ok=True)
            row.update(output=str(out),source_hash_preserved=digest(case['source'])==case['sha256']==digest(out/'Original.pdf'),
                output_hashes_match=all(digest(out/n)==v for n,v in state['output_hashes'].items()),
                translation_tracking=quality['translation_tracking'],rendered_prose=quality.get('rendered_prose'),
                meaning_assurance=quality.get('meaning_assurance'),checks=quality['checks'],ocr_pages=quality['ocr_source_pages'],
                manual_target_edits=quality['manually_edited_targets'])
            from babelko.render_coverage import inspect as check_prose
            from babelko.validation import inspect_output
            from babelko.assurance import REVISION
            from babelko.assurance import accepted
            from babelko.hybrid import errors,literal
            hybrid=read(job/'hybrid-summary.json');contract_issues=[]
            for key in hybrid['active_keys']:
                record=read(job/'hybrid'/(key+'.json'))
                faults=errors(record['source'],record.get('final',''),record['label'])
                if not literal(record['source']) and not accepted(record):faults.append('current evidence missing')
                if faults:contract_issues.append(dict(key=key,issues=faults))
            row['current_contract_issues']=contract_issues
            row.update(protocol=quality['protocol'],ocr_revision=quality['ocr_revision'],
                post_export_prose=check_prose(out/'Korean.pdf',job/'intermediate/translate_tracking.json'),
                post_export_bounds=inspect_output(out/'Korean.pdf',state['selected']),
                input_transformations=quality.get('input_transformations',{}),
                source_flow_merges=len(read(job/'source-flow-repairs.json')) if (job/'source-flow-repairs.json').exists() else 0)
            with fitz.open(out/'Original.pdf') as source,fitz.open(out/'Korean.pdf') as ko,fitz.open(out/'Bilingual.pdf') as dual:
                row['pages']=len(ko)
                row['page_counts_match']=len(ko)==len(dual)==len(state['selected'])
                row['original_faces_equal']=[source[index].get_pixmap(alpha=False).samples==dual[i].get_pixmap(clip=source[index].rect,alpha=False).samples for i,index in enumerate(state['selected'])]
                if case['key']=='controlled' and len(ko)>3:
                    src=source[3].get_text('words');dst=ko[3].get_text('words');checks=[]
                    for value in ['0.25','-2.5','0.50','+3.0']:
                        a=next((w for w in src if w[4]==value),None);targets=[w for w in dst if w[4]==value]
                        distance=min((math.hypot((a[0]+a[2]-b[0]-b[2])/2,(a[1]+a[3]-b[1]-b[3])/2) for b in targets),default=None) if a else None
                        checks.append(dict(value=value,present=bool(targets),source_position_distance_pt=distance))
                    row['controlled_table_cells']=checks
            row['current_auditor']=row.get('meaning_assurance',{}).get('revision')==REVISION
            row['verification_status']='passed' if (state['status']=='completed' and not contract_issues and row['current_auditor'] and row['source_hash_preserved'] and row['output_hashes_match'] and row['page_counts_match'] and all(row['original_faces_equal']) and row['post_export_prose']['status']=='passed' and row['post_export_bounds']['status']=='passed' and row.get('meaning_assurance',{}).get('status')=='passed' and all(c['present'] and c['source_position_distance_pt']<8 for c in row.get('controlled_table_cells',[]))) else 'failed'
            stamp=dest/'rendered-hash.json'
            if not stamp.exists() or read(stamp).get('sha256')!=digest(out/'Korean.pdf'):
                subprocess.run([str(poppler),'-png','-scale-to','1100',str(out/'Korean.pdf'),str(dest/'page')],check=True,creationflags=subprocess.CREATE_NO_WINDOW,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                save(stamp,dict(sha256=digest(out/'Korean.pdf')))
            files=sorted(dest.glob('page-*.png'))
            for start in range(0,len(files),6):
                chunk=files[start:start+6];sheet=Image.new('RGB',(1200,math.ceil(len(chunk)/2)*820),'#dce3e8');draw=ImageDraw.Draw(sheet)
                for i,p in enumerate(chunk):
                    with Image.open(p) as im:
                        thumb=ImageOps.contain(im.convert('RGB'),(580,780));x=(i%2)*600+(600-thumb.width)//2;y=(i//2)*820+30
                        sheet.paste(thumb,(x,y));draw.text(((i%2)*600+12,(i//2)*820+8),f'{case["key"]} page {start+i+1}',fill='black')
                sheet.save(dest/f'overview-{start//6+1}.png')
            save(dest/'verification.json',row)
            gallery=''.join(f'<a href="{link(p)}"><img src="{link(p)}"></a>' for p in sorted(dest.glob('overview-*.png')))
            files=' · '.join(f'<a href="{link(out/n)}">{n}</a>' for n in ['Korean.pdf','Bilingual.pdf','Quality.json'])
            sections.append('<section><h2>'+html.escape(case['key'])+'</h2><p>'+html.escape(case['kind'])+'</p><p>'+files+'</p>'+gallery+'</section>')
        rows.append(row)
    summary=dict(scope='Selected pages of external documents plus authored layout controls. Automated evidence is not semantic certification.',
        sources=[{k:c[k] for k in ['key','url','pages','sha256','total_pages']} for c in read(base/'manifest.json')['cases']],results=rows)
    save(base/'assessment.json',summary)
    totals=dict(documents=len(rows),pages=sum(r.get('pages',0) for r in rows),
        passed=sum(r.get('verification_status')=='passed' for r in rows),
        source_faces_matched=sum(sum(r.get('original_faces_equal',[])) for r in rows),
        tracked_units=sum(r.get('translation_tracking',{}).get('parsed_translation_units',0) for r in rows),
        untranslated_tracked_units=sum(r.get('translation_tracking',{}).get('units_with_no_output',0) for r in rows),
        manual_target_edits=sum(r.get('manual_target_edits',0) for r in rows),semantic_accuracy='not_certified')
    save(base/'final-summary.json',totals)
    table='<table><tr><th>자료</th><th>작업 상태</th><th>후속 검사</th><th>검사 쪽 수</th><th>추적 출력 누락</th><th>원문면 일치</th></tr>'
    for r in rows:
        table+='<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in [r['key'],r['status'],r.get('verification_status','—'),r.get('pages','—'),r.get('translation_tracking',{}).get('units_with_no_output','—'),all(r.get('original_faces_equal',[])) if r.get('original_faces_equal') else '—'])+'</tr>'
    table+='</table>'
    sources='<ul>'+''.join('<li>'+('<a href="'+html.escape(c['url'],quote=True)+'">'+html.escape(c['key'])+'</a>' if c['url'] else 'controlled: 직접 작성한 배치 시험본')+' · 선택 쪽 '+html.escape(c['pages'] or '전체')+'</li>' for c in read(base/'manifest.json')['cases'])+'</ul>'
    body='''<!doctype html><meta charset="utf-8"><title>BabelKO 문서 다양성 검사</title><style>body{font:16px/1.7 'Malgun Gothic',sans-serif;max-width:1250px;margin:auto;padding:32px;background:#edf3f5;color:#183848}section{background:white;padding:22px;margin:22px 0}img{width:100%}table{width:100%;border-collapse:collapse}td,th{padding:10px;border-bottom:1px solid #bbcbd1;text-align:left}a{color:#006f7a}</style><h1>문서 다양성 및 자동 교정 검사</h1><p>사용자 예시를 제외한 공개 자료의 지정 쪽과 직접 작성한 시험본입니다. 번역문 수동 수정 없이 프로그램으로 처리합니다. 시간 비교는 수행하지 않았습니다. 추적 입력 누락·숫자/서식·근거 대조·출력 본문·원문면 보존을 검사하며 독립 전문가의 의미 정확도 인증은 아닙니다. 실패·미실행 사례도 그대로 표시합니다.</p>'''
    meaning='<h2>의미 대조 시험</h2><p>실제 논문의 정확도 점수가 아니라, 정해진 정상·오류 문장을 구분하는 시험입니다. 수정된 번역의 재통과는 같은 로컬 모델과 구조 검사로 판단합니다.</p>'
    for file in meaning_results:
        result=read(file)
        component=' · 모델 단독 '+str(result['model_correct'])+'/'+str(result['judgments']) if 'model_correct' in result else ' · 모델 단독 시험'
        meaning+='<p><a href="'+link(file)+'">'+html.escape(file.parent.name)+'</a>: '+html.escape(str(result['correct']))+'/'+html.escape(str(result['judgments']))+' 구분 · 미탐 '+html.escape(str(len(result['missed_defects'])))+' · 오탐 '+html.escape(str(len(result['false_alarms'])))+' · 자동 수정 후 재검사 통과 '+html.escape(str(result['repair_passes']))+'건'+component+'</p>'
    scope='<p>자동 후속 검사 통과 '+str(totals['passed'])+'/'+str(totals['documents'])+'종 · '+str(totals['pages'])+'쪽 · 추적 번역 입력 '+str(totals['tracked_units'])+'개 · 추적 출력 누락 '+str(totals['untranslated_tracked_units'])+'개 · 원문면 픽셀 일치 '+str(totals['source_faces_matched'])+'쪽 · 번역문 수동 수정 '+str(totals['manual_target_edits'])+'회. 이 수치는 인식되지 않은 원문 누락이나 모든 의미 오류가 없다는 보증이 아닙니다.</p>'
    (base/'Assessment.html').write_text(body+scope+table+meaning+sources+''.join(sections),encoding='utf-8')
    print(json.dumps([dict(key=r['key'],status=r['status'],pages=r.get('pages'),error=r.get('error')) for r in rows],ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',type=Path,default=project()/'test_vault/accuracy-diverse-20261021');p.add_argument('--meaning-results',type=Path,action='append',default=[]);a=p.parse_args();inspect(a.base.resolve(),[p.resolve() for p in a.meaning_results])
