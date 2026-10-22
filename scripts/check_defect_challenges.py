"""Real local challenge validation: fixed controls and read-only failed records."""
import argparse,copy,json
from contextlib import nullcontext
from types import SimpleNamespace
from pathlib import Path
from babelko.storage import read,save,project


def main(job,output,running_job=None):
    from babelko.engine import LocalEngine
    from babelko.hybrid import HybridTranslator,errors
    from babelko.assurance import reconsider,checked,tasks,fingerprint,REVISION
    from pdf2zh_next.config.model import SettingsModel
    from pdf2zh_next.config.translate_engine_model import OpenAISettings
    from pdf2zh_next.translator.base_rate_limiter import BaseRateLimiter
    output.mkdir(parents=True,exist_ok=False);records=[]
    for name in ['meaning_reserved_cases.json','meaning_boundary_cases.json']:
        for case in read(project()/'tests'/name):
            for variant in ['good','bad']:
                r=dict(key=case['id']+'-'+variant,source=case['source'],final=case[variant],context='',label='text',neighbors=case.get('neighbors',[]))
                checks=[dict(**t,verdict='partial',evidence=[],reason='A previous check alleges a meaning difference; verify against the supplied wording.') for t in tasks(r['source'],r['final'])]
                r['assurance']=dict(revision=REVISION,fingerprint=fingerprint(r),checks=checks,status='repair')
                records.append((r,variant=='bad','fixed_control'))
    for item in read(job/'pending-review.json')['pending']:
        r=read(job/'hybrid'/(item['key']+'.json'))
        if r.get('final') and checked(r):records.append((r,None,'failed_candidate'))
    snapshot=read(job/'state.json')['snapshot'];snapshot={**snapshot,'model':snapshot['editor'],'review_slots':1}
    results=[]
    context=LocalEngine(output,snapshot=snapshot)
    if running_job:
        import psutil
        running=read(running_job/'state.json');owner=psutil.Process(running['pid'])
        if abs(owner.create_time()-running['process_created'])>=1 or 'babelko.worker' not in owner.cmdline():raise RuntimeError('실행 중 작업 소유권 불일치')
        processes=[p for p in owner.children(recursive=True) if p.name().lower()=='llama-server.exe']
        if len(processes)!=1:raise RuntimeError('실행 중인 앱 소유 엔진을 특정할 수 없습니다.')
        args=processes[0].cmdline()
        if Path(args[args.index('-m')+1]).resolve()!=Path(snapshot['model']['path']).resolve():raise RuntimeError('실행 중 모델이 검수 모델과 다릅니다.')
        if args[args.index('--host')+1]!='127.0.0.1':raise RuntimeError('로컬 전용 엔진이 아닙니다.')
        context=nullcontext(SimpleNamespace(model=snapshot['model'],url='http://127.0.0.1:'+args[args.index('--port')+1]+'/v1',key=args[args.index('--api-key')+1]))
    with context as engine:
        if not running_job:engine.start(lambda *_:None)
        settings=SettingsModel(translate_engine_settings=OpenAISettings(openai_model=engine.model['id'],openai_base_url=engine.url,openai_api_key=engine.key,openai_timeout='300'))
        translator=HybridTranslator(settings,BaseRateLimiter(),output);translator.phase='review'
        try:
            for r,expected,kind in records:
                try:
                    outcome=reconsider(r,r['assurance'],translator._request)
                    detected=outcome['status']!='passed' or bool(errors(r['source'],r['final'],r['label']))
                    row=dict(key=r['key'],kind=kind,expected_defect=expected,detected=detected,
                        correct=detected==expected if expected is not None else None,outcome=outcome)
                except Exception as exc:row=dict(key=r['key'],kind=kind,error=str(exc),correct=False)
                results.append(row);save(output/'results.json',results)
                print(json.dumps({k:v for k,v in row.items() if k!='outcome'},ensure_ascii=False),flush=True)
        finally:translator.client.close()
    controls=[r for r in results if r['kind']=='fixed_control']
    summary=dict(controls=len(controls),correct=sum(bool(r.get('correct')) for r in controls),
        errors=[r['key'] for r in results if r.get('error')],failed_candidates=len(results)-len(controls),
        failed_candidates_withdrawn=sum(not r.get('detected',True) for r in results if r['kind']=='failed_candidate'))
    save(output/'summary.json',summary);print(json.dumps(summary),flush=True)
    if summary['correct']!=summary['controls']:raise RuntimeError('Challenge controls regressed; do not deploy this policy.')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--job',required=True,type=Path);parser.add_argument('--output',required=True,type=Path);parser.add_argument('--running-job',type=Path)
    args=parser.parse_args();main(args.job,args.output,args.running_job)
