"""Real local-model defect detection and automatic repair, not self-scored quality.

Good/bad labels are fixed authored controls; responses, defects and failures
are retained. No source/target replacements or metric-based exclusions.
"""
import argparse,json,threading
from pathlib import Path
from babelko.storage import project,read,save


def main(output,limit=None,cases_path=None):
    from babelko.engine import LocalEngine
    from babelko.hybrid import HybridTranslator,errors
    from babelko.assurance import audit,accepted,REVISION
    from babelko.upstream import prepare
    prepare()
    from pdf2zh_next.config.model import SettingsModel
    from pdf2zh_next.config.translate_engine_model import OpenAISettings
    from pdf2zh_next.translator.base_rate_limiter import BaseRateLimiter
    output.mkdir(parents=True,exist_ok=True)
    cases_path=cases_path or project()/'tests/meaning_cases.json'
    cases=read(cases_path)
    if limit:cases=cases[:limit]
    with LocalEngine(output) as engine:
        engine.start(lambda *_:None)
        settings=SettingsModel(translate_engine_settings=OpenAISettings(openai_model=engine.model['id'],openai_base_url=engine.url,openai_api_key=engine.key,openai_timeout='300'))
        translator=HybridTranslator(settings,BaseRateLimiter(),output);translator.phase='review'
        results=[]
        try:
            for case in cases:
                for label in ['good','bad']:
                    r=dict(key=case['id']+'-'+label,source=case['source'],label='text',context='',neighbors=case.get('neighbors',[]),final=case[label])
                    try:
                        result=audit(r,translator._request);r['assurance']=result
                        model_detected=result['status']!='passed';contract_errors=errors(r['source'],r['final'])
                        detected=model_detected or bool(contract_errors)
                        row=dict(id=case['id'],label=label,detected=detected,model_detected=model_detected,
                            contract_errors=contract_errors,correct=detected==(label=='bad'),evidence=result)
                        if label=='bad' and detected:
                            try:
                                translator.ensure_assured(r)
                                row.update(repaired=accepted(r) and not errors(r['source'],r['final']),final=r['final'])
                            except Exception as exc:row.update(repaired=False,repair_error=type(exc).__name__+': '+str(exc))
                    except Exception as exc:row=dict(id=case['id'],label=label,error=type(exc).__name__+': '+str(exc),correct=False)
                    results.append(row);save(output/'results.json',results);print(case['id'],label,row.get('correct'),row.get('error',''),flush=True)
        finally:translator.client.close()
    from babelko.storage import digest
    summary=dict(auditor_revision=REVISION,cases_file=cases_path.name,cases_sha256=digest(cases_path),cases=len(cases),judgments=len(results),correct=sum(r['correct'] for r in results),
        detection_scope='model audit plus deterministic contract; component scores retained',
        model_correct=sum(r.get('model_detected')==(r['label']=='bad') for r in results if 'model_detected' in r),
        model_missed_defects=[r['id'] for r in results if r['label']=='bad' and not r.get('model_detected')],
        missed_defects=[r['id'] for r in results if r['label']=='bad' and not r.get('detected')],
        false_alarms=[r['id'] for r in results if r['label']=='good' and r.get('detected')],
        repair_passes=sum(bool(r.get('repaired')) for r in results),errors=[r['id'] for r in results if r.get('error') or r.get('repair_error')],
        caveat='Authored controls, not independent accuracy certification. Repair success is the same model evidence gate plus structural checks.')
    save(output/'summary.json',summary);print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=project()/'test_vault/meaning-controls-20261021');p.add_argument('--limit',type=int);p.add_argument('--cases',type=Path);a=p.parse_args();main(a.output.resolve(),a.limit,a.cases)
