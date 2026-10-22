"""Full versus dependency-aware review on authored local repair controls."""
import argparse,copy,json,time
from pathlib import Path
from babelko.storage import read,save


def main(output,job):
    from babelko.assurance import audit,accepted
    from babelko.assurance_reuse import preserve
    from babelko.engine import LocalEngine
    from babelko.hybrid import HybridTranslator,errors
    from pdf2zh_next.config.model import SettingsModel
    from pdf2zh_next.config.translate_engine_model import OpenAISettings
    from pdf2zh_next.translator.base_rate_limiter import BaseRateLimiter
    source=['The research team collects interview transcripts.','Art therapists document workshop observations.',
        'The field supervisor stores consent forms.','Clinical staff review participant diaries.',
        'Independent coders organize descriptive categories.','Research assistants archive session recordings.',
        'Community partners discuss recruitment procedures.','Project coordinators arrange feedback meetings.',
        'Qualitative researchers describe coding decisions.','External reviewers examine analytical notes.']
    target=['연구팀은 면담 전사본을 수집한다.','미술치료사들은 워크숍 관찰 내용을 기록한다.',
        '현장 지도자는 동의서를 보관한다.','임상 직원들은 참여자 일지를 검토한다.',
        '독립 코더들은 서술적 범주를 정리한다.','연구 보조원들은 회기 녹화 자료를 보관한다.',
        '지역사회 협력자들은 모집 절차를 논의한다.','사업 조정자들은 의견 수렴 회의를 마련한다.',
        '질적 연구자들은 코딩 결정을 설명한다.','외부 검토자들은 분석 메모를 살펴본다.']
    base=dict(key='control',label='text',context='Research records',neighbors=[],source=' '.join(source),final=' '.join(target).replace('동의서를','청구서를'))
    state=read(job/'state.json');snapshot={**state['snapshot'],'model':state['snapshot']['editor']}
    output.mkdir(parents=True,exist_ok=False);results=[]
    with LocalEngine(output,snapshot=snapshot) as engine:
        engine.start(lambda message,*_:print(message,flush=True))
        settings=SettingsModel(translate_engine_settings=OpenAISettings(openai_model=engine.model['id'],openai_base_url=engine.url,openai_api_key=engine.key,openai_timeout='300'))
        translator=HybridTranslator(settings,BaseRateLimiter(),output);translator.phase='review'
        try:
            base['assurance']=audit(base,translator._request);save(output/'base.json',base)
            if accepted(base):raise RuntimeError('Baseline missed the deliberately wrong invoice noun; no reuse benchmark is valid.')
            cases=[('correct',target[2],False),('wrong-action','현장 지도자는 동의서를 폐기한다.',True),
                ('negation','현장 지도자는 동의서를 보관하지 않는다.',True),('quantity','현장 지도자는 동의서 7개를 보관한다.',True)]
            for n,(name,repaired,bad) in enumerate(cases):
                for mode in (['full','reuse'] if n%2==0 else ['reuse','full']):
                    r=copy.deepcopy(base);preserve(r);r['final']=' '.join(target[:2]+[repaired]+target[3:]);r.pop('assurance')
                    if mode=='full':r.pop('audit_base')
                    before=translator.requests;start=time.perf_counter();r['assurance']=audit(r,translator._request)
                    outcome=dict(case=name,mode=mode,expected_defect=bad,detected=not accepted(r) or bool(errors(r['source'],r['final'])),
                        requests=translator.requests-before,seconds=round(time.perf_counter()-start,3),
                        reused_checks=r['assurance']['reused_checks'],evidence=r['assurance'])
                    results.append(outcome);save(output/'results.json',results)
                    print(json.dumps({k:v for k,v in outcome.items() if k!='evidence'},ensure_ascii=False),flush=True)
        finally:translator.client.close()
    summary=dict(controls=len(cases),correct=sum(x['detected']==x['expected_defect'] for x in results),
        comparisons=len(results),modes={m:dict(requests=sum(x['requests'] for x in results if x['mode']==m),
            seconds=round(sum(x['seconds'] for x in results if x['mode']==m),3)) for m in ['full','reuse']},
        caveat='Authored independent-sentence controls, not whole-job throughput or independent semantic certification.')
    save(output/'summary.json',summary);print(json.dumps(summary,ensure_ascii=False),flush=True)
    if summary['correct']!=summary['comparisons']:raise RuntimeError('Repair-control accuracy regression; do not promote reuse.')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--job',type=Path,required=True)
    args=parser.parse_args();main(args.output,args.job)
