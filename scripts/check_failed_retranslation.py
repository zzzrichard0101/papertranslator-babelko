"""Exercise one saved failed unit on a private copy with the installed local editor."""
import argparse,copy,json,time,uuid
from pathlib import Path
import httpx,openai
from babelko.engine import LocalEngine
from babelko.hybrid import HybridTranslator,errors
from babelko.storage import read,save


def main(job,key,output):
    state=read(job/'state.json')
    if state['status'] not in {'failed','cancelled'}:raise RuntimeError('검증 대상 작업이 아직 실행 중입니다.')
    original=read(job/'hybrid'/(key+'.json'))
    if key not in {v['key'] for v in read(job/'pending-review.json')['pending']}:
        raise ValueError('현재 미해결 문단이 아닙니다.')
    output.mkdir(parents=True,exist_ok=True);(output/'responses').mkdir(exist_ok=True)
    translator=object.__new__(HybridTranslator)
    translator.folder=output;translator.checkpoints=output/'hybrid';translator.checkpoints.mkdir(exist_ok=True)
    translator.cancel=lambda:False;translator.retries=0;translator.hard_failures=[]
    translator.stats=dict(retranslated=0,audited=0,repair_rounds=0,patched=0)
    record=copy.deepcopy(original)
    snapshot={**state['snapshot'],'model':state['snapshot']['editor'],'review_slots':1}
    with LocalEngine(output,cancel=lambda:False,snapshot=snapshot) as engine:
        engine.start(lambda message:print(message,flush=True))
        with httpx.Client(trust_env=False,timeout=300) as http:
            client=openai.OpenAI(base_url=engine.url,api_key=engine.key,timeout=300,max_retries=0,http_client=http)
            def request(messages,schema=None):
                options=dict(model=engine.model['id'],messages=messages,temperature=.1,max_tokens=2400,seed=42)
                if schema:options['response_format']=dict(type='json_schema',json_schema=dict(name='translation',strict=True,schema=schema))
                began=time.monotonic();response=client.chat.completions.create(**options)
                save(output/'responses'/(uuid.uuid4().hex+'.json'),dict(messages=messages,response=response.model_dump(),seconds=time.monotonic()-began))
                if response.choices[0].finish_reason=='length':raise ValueError('번역 응답이 길이 제한으로 끊겼습니다.')
                return (response.choices[0].message.content or '').strip()
            translator._request=request
            try:
                translator.retranslate(record)
                translator.ensure_assured(record)
                outcome=dict(status='passed',structural_errors=errors(record['source'],record['final'],record['label']),
                    assurance=record.get('assurance',{}).get('status'),requests=len(list((output/'responses').glob('*.json'))))
            except Exception as exc:
                outcome=dict(status='failed',error=str(exc),final_error=record.get('final_error'),
                    structural_errors=errors(record['source'],record.get('final') or '',record['label']),
                    requests=len(list((output/'responses').glob('*.json'))))
    save(output/'result.json',dict(key=key,outcome=outcome,record=record))
    print(json.dumps(outcome,ensure_ascii=False),flush=True)
    if outcome['status']!='passed':raise RuntimeError('실제 로컬 모델 검증 실패')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--job',type=Path,required=True)
    parser.add_argument('--key',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();main(args.job,args.key,args.output)
