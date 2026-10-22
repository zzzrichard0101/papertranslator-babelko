"""Compare audit execution on frozen local inputs; never edit user translations."""
import argparse,copy,importlib.util,json,time
from pathlib import Path
from babelko.storage import read,save,project


def main(output,baseline_path,job=None):
    from babelko.assurance import audit,audit_many,group_fits,accepted,EXECUTION
    from babelko.engine import LocalEngine
    from babelko.hybrid import HybridTranslator,errors
    from pdf2zh_next.config.model import SettingsModel
    from pdf2zh_next.config.translate_engine_model import OpenAISettings
    from pdf2zh_next.translator.base_rate_limiter import BaseRateLimiter
    spec=importlib.util.spec_from_file_location('baseline_auditor',baseline_path)
    baseline=importlib.util.module_from_spec(spec);spec.loader.exec_module(baseline)
    output.mkdir(parents=True,exist_ok=True);items=[]
    for filename in ['meaning_cases.json','meaning_reserved_cases.json','meaning_boundary_cases.json']:
        for case in read(project()/'tests'/filename):
            for label in ['good','bad']:
                items.append(dict(id=case['id']+'-'+label,kind='control',expected=label=='bad',
                    record=dict(source=case['source'],final=case[label],context='',neighbors=case.get('neighbors',[]))))
    snapshot=None
    if job:
        state=read(job/'state.json');snapshot={**state['snapshot'],'model':state['snapshot']['editor']}
        rows=[read(job/'hybrid'/(key+'.json')) for key in read(job/'pending-review.json')['active_keys']]
        candidates=sorted([r for r in rows if accepted(r) and len(r['source'])>80],key=lambda r:len(r['source']))
        for n in range(8):
            r=candidates[round(n*(len(candidates)-1)/7)]
            items.append(dict(id='book-'+str(n),kind='book',expected=None,record={k:r.get(k) for k in ['source','final','context','neighbors','formula_hints']}))
    groups=[];current=[]
    for item in items:
        if current and not group_fits([x['record'] for x in current+[item]]):groups.append(current);current=[]
        current.append(item)
    if current:groups.append(current)
    results=[]
    with LocalEngine(output,snapshot=snapshot) as engine:
        engine.start(lambda message,*_:print(message,flush=True))
        settings=SettingsModel(translate_engine_settings=OpenAISettings(openai_model=engine.model['id'],openai_base_url=engine.url,openai_api_key=engine.key,openai_timeout='300'))
        translator=HybridTranslator(settings,BaseRateLimiter(),output);translator.phase='review'
        try:
            for n,group in enumerate(groups):
                # Alternate execution order to reduce warm-prefix/order bias.
                for mode in (['baseline','grouped'] if n%2==0 else ['grouped','baseline']):
                    records=[copy.deepcopy(x['record']) for x in group];before=translator.requests;started=time.perf_counter()
                    if mode=='baseline':outcomes=[baseline.audit(r,translator._request) for r in records]
                    else:
                        try:outcomes=audit_many(records,translator._request)
                        except (ValueError,RuntimeError):outcomes=[audit(r,translator._request) for r in records]
                    duration=time.perf_counter()-started
                    rows=[]
                    for item,r,outcome in zip(group,records,outcomes):
                        model_detected=outcome['status']!='passed';contract=errors(r['source'],r['final'])
                        detected=model_detected or bool(contract)
                        rows.append(dict(id=item['id'],kind=item['kind'],expected=item['expected'],detected=detected,
                            model_detected=model_detected,contract_errors=contract,
                            correct=detected==item['expected'] if item['expected'] is not None else None,evidence=outcome))
                    results.append(dict(group=n,mode=mode,requests=translator.requests-before,seconds=duration,items=rows))
                    save(output/'results.json',results);print('group',n+1,'/',len(groups),mode,'calls',translator.requests-before,'seconds',round(duration,2),flush=True)
        finally:translator.client.close()
    summary=dict(execution=EXECUTION,controls=sum(x['kind']=='control' for x in items),book_samples=sum(x['kind']=='book' for x in items),modes={})
    for mode in ['baseline','grouped']:
        batches=[r for r in results if r['mode']==mode];rows=[x for r in batches for x in r['items']];controls=[x for x in rows if x['kind']=='control']
        summary['modes'][mode]=dict(requests=sum(r['requests'] for r in batches),seconds=round(sum(r['seconds'] for r in batches),2),
            correct=sum(x['correct'] for x in controls),model_correct=sum(x['model_detected']==x['expected'] for x in controls),
            missed=[x['id'] for x in controls if x['expected'] and not x['detected']],false_alarms=[x['id'] for x in controls if not x['expected'] and x['detected']])
    by_mode={mode:{x['id']:x['detected'] for r in results if r['mode']==mode for x in r['items'] if x['kind']=='book'} for mode in ['baseline','grouped']}
    summary['book_agreement']=sum(v==by_mode['grouped'][k] for k,v in by_mode['baseline'].items())
    summary['caveat']='Fixed authored controls and agreement on frozen book samples, not independent semantic certification or whole-job speed.'
    save(output/'summary.json',summary);print(json.dumps(summary,ensure_ascii=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--baseline',type=Path,required=True);parser.add_argument('--job',type=Path)
    args=parser.parse_args();main(args.output,args.baseline,args.job)
