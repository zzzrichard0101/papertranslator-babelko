"""Isolated local ABBA audit throughput and fixed-verdict regression experiment.

Run only after the app-owned translation worker has checkpointed and stopped.
No user targets are changed. Results include full, private model evidence.
"""
import argparse,copy,datetime,json,os,statistics,subprocess,sys,threading,time,zipfile
from contextlib import contextmanager
from pathlib import Path
from babelko.storage import read,save


@contextmanager
def checkpoint_pause(job):
    """Explicit CLI opt-in, only a verified worker of THIS job; always resume."""
    import psutil
    from babelko.storage import root,project
    if job.resolve().parent!=(root()/'jobs').resolve():raise ValueError('앱 소유 작업 경로가 아닙니다.')
    state=read(job/'state.json');active=state['status'] in {'queued','preparing','translating','validating'}
    if not active:yield;return
    worker=psutil.Process(state['pid']);args=worker.cmdline()
    if 'babelko.worker' not in args or not any(Path(a).resolve()==job.resolve() for a in args if a==str(job)):
        raise RuntimeError('작업 프로세스 소유권 확인 실패')
    if abs(worker.create_time()-state['process_created'])>=1:raise RuntimeError('작업 PID가 재사용되었습니다.')
    if (job/'cancel').exists():raise RuntimeError('사용자가 이미 취소한 작업은 자동 재개하지 않습니다.')
    (job/'cancel').touch();print('Checkpoint pause requested.',flush=True)
    try:
        worker.wait(timeout=55)
        stopped=read(job/'state.json')
        if stopped['status'] not in {'cancelled','failed','completed'}:raise RuntimeError('체크포인트 정리 완료를 확인하지 못했습니다.')
        stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
        backup=job/'checkpoint-backups'/('before-concurrent-audit-'+stamp+'.zip');backup.parent.mkdir(exist_ok=True)
        files=list((job/'hybrid').glob('*.json'))+[p for p in job.glob('*.json') if p.is_file()]
        with zipfile.ZipFile(backup,'x',compression=zipfile.ZIP_DEFLATED) as archive:
            for path in files:archive.write(path,path.relative_to(job))
        with zipfile.ZipFile(backup) as archive:
            if archive.testzip() is not None or len(archive.namelist())!=len(files):raise RuntimeError('체크포인트 백업 검사 실패')
        print('Checkpoint backup verified: '+str(len(files))+' files.',flush=True)
        yield
    finally:
        if not worker.is_running() and read(job/'state.json')['status']!='completed':
            (job/'cancel').unlink(missing_ok=True)
            stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S');log=job/('resume-after-concurrent-audit-'+stamp+'.log')
            with log.open('a',encoding='utf-8') as stream:
                process=subprocess.Popen([sys.executable,'-u','-m','babelko.worker',str(job)],cwd=project(),
                    env={**os.environ,'PYTHONIOENCODING':'utf-8'},stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
            save(job/'resume-launch.json',dict(pid=process.pid,log=str(log),reason='Concurrent audit benchmark finished; original snapshot and checkpoints retained.'))
            print('Original job resumed, launcher PID '+str(process.pid),flush=True)


def groups(records):
    from babelko.assurance import group_fits
    pending=[]
    for row in records:
        if pending and not group_fits(pending+[row]):yield pending;pending=[]
        pending.append(row)
    if pending:yield pending


def corpus(job):
    from babelko.assurance import accepted,segments
    rows=[];base=Path(__file__).resolve().parents[1]
    for name in ['meaning_reserved_cases.json','meaning_boundary_cases.json']:
        for case in read(base/'tests'/name):
            for variant in ['good','bad']:
                rows.append(dict(key=case['id']+'-'+variant,label='text',source=case['source'],final=case[variant],
                    neighbors=case.get('neighbors',[]),context='',expected_defect=variant=='bad',kind='authored_control'))
    # Long audit workloads supplement short fixed controls. Prior model
    # acceptance is regression evidence, explicitly NOT an independent gold.
    for path in sorted((job/'hybrid').glob('*.json')):
        row=read(path)
        if accepted(row) and 5<=len(segments(row['source']))<=10:
            rows.append({k:row.get(k) for k in ['key','label','source','final','neighbors','context','formula_hints']})
            rows[-1].update(expected_defect=False,kind='prior_accepted_regression')
            if sum(r['kind']=='prior_accepted_regression' for r in rows)>=4:break
    return rows


def main(output,job):
    from babelko.engine import LocalEngine
    from babelko.hybrid import HybridTranslator,errors
    from babelko.assurance import audit_many
    from babelko.review_pool import ReviewPool
    from pdf2zh_next.config.model import SettingsModel
    from pdf2zh_next.config.translate_engine_model import OpenAISettings
    from pdf2zh_next.translator.base_rate_limiter import BaseRateLimiter
    output.mkdir(parents=True,exist_ok=False)
    rows=corpus(job);save(output/'frozen-corpus.json',rows)
    snapshot=read(job/'state.json')['snapshot'];snapshot={**snapshot,'model':snapshot['editor']}
    results=[]
    for round_id,slots in enumerate([1,2,2,1]):
        folder=output/('round-'+str(round_id+1)+'-slots-'+str(slots));folder.mkdir()
        vram=[];stop=threading.Event()
        def sample():
            while not stop.is_set():
                try:
                    raw=subprocess.check_output(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits'],creationflags=subprocess.CREATE_NO_WINDOW,timeout=3)
                    vram.append(int(raw.decode().strip().splitlines()[0]))
                except (OSError,ValueError,subprocess.SubprocessError):pass
                stop.wait(1)
        sampler=threading.Thread(target=sample,daemon=True);sampler.start()
        began=time.perf_counter()
        try:
            with LocalEngine(folder,snapshot={**snapshot,'review_slots':slots}) as engine:
                engine.start(lambda message,*_:print(message,flush=True))
                load_seconds=time.perf_counter()-began
                settings=SettingsModel(translate_engine_settings=OpenAISettings(openai_model=engine.model['id'],openai_base_url=engine.url,openai_api_key=engine.key,openai_timeout='300'))
                translator=HybridTranslator(settings,BaseRateLimiter(),folder);translator.phase='review'
                try:
                    audit_many([rows[0]],translator._request)  # same warm-up in every fresh server
                    warm_files=set((folder/'responses').glob('*.json'))
                    before=translator.requests;start=time.perf_counter();outcomes=[]
                    if slots==1:
                        for group in groups(copy.deepcopy(rows)):outcomes.extend(audit_many(group,translator._request))
                    else:
                        pool=ReviewPool(translator._request,lambda:False,2)
                        try:
                            for group in groups(copy.deepcopy(rows)):
                                pool.submit(group)
                                if len(pool.pending)==2:
                                    for records,values in pool.drain():
                                        if values is None:raise RuntimeError('동시 검수 계약 실패')
                                        outcomes.extend(values)
                            for records,values in pool.drain():
                                if values is None:raise RuntimeError('동시 검수 계약 실패')
                                outcomes.extend(values)
                        finally:pool.close()
                    seconds=time.perf_counter()-start
                    responses=[read(p) for p in (folder/'responses').glob('*.json') if p not in warm_files]
                    latencies=sorted(r['seconds'] for r in responses)
                    assert len(outcomes)==len(rows)
                    evaluations=[dict(key=r['key'],kind=r['kind'],expected_defect=r['expected_defect'],
                        detected=outcome['status']!='passed' or bool(errors(r['source'],r['final'],r['label'])),
                        evidence=outcome) for r,outcome in zip(rows,outcomes)]
                    result=dict(round=round_id+1,slots=slots,per_request_context=8192,kv_type='f16',load_seconds=round(load_seconds,3),
                        seconds=round(seconds,3),requests=translator.requests-before,peak_vram_mib=max(vram,default=None),
                        request_p50_seconds=round(statistics.median(latencies),3),
                        request_p95_seconds=round(latencies[min(len(latencies)-1,int(len(latencies)*.95))],3),
                        prompt_tokens=sum(r['response']['usage']['prompt_tokens'] for r in responses),
                        output_tokens=sum(r['response']['usage']['completion_tokens'] for r in responses),
                        controls_correct=sum(v['detected']==v['expected_defect'] for v in evaluations if v['kind']=='authored_control'),
                        controls=sum(v['kind']=='authored_control' for v in evaluations),
                        false_negatives=[v['key'] for v in evaluations if v['expected_defect'] and not v['detected']],
                        false_positives=[v['key'] for v in evaluations if not v['expected_defect'] and v['detected']],evaluations=evaluations)
                    results.append(result);save(output/'results.json',results)
                    print(json.dumps({k:v for k,v in result.items() if k!='evaluations'},ensure_ascii=False),flush=True)
                finally:translator.client.close()
        finally:stop.set();sampler.join(timeout=4)
    medians={str(slots):statistics.median(r['seconds'] for r in results if r['slots']==slots) for slots in [1,2]}
    summary=dict(records=len(rows),rounds=4,median_audit_seconds=medians,
        audit_time_reduction_percent=round(100*(1-medians['2']/medians['1']),2),
        all_authored_controls_correct=all(r['controls_correct']==r['controls'] for r in results),
        caveat='Audit workload ABBA, not whole-book end-to-end speed or semantic certification; fixed controls plus separately labeled prior-model regression cases. No document text left this PC.')
    save(output/'summary.json',summary);print(json.dumps(summary,ensure_ascii=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--job',required=True,type=Path);parser.add_argument('--output',required=True,type=Path);parser.add_argument('--pause-job',action='store_true')
    args=parser.parse_args()
    if args.pause_job:
        with checkpoint_pause(args.job):main(args.output,args.job)
    else:main(args.output,args.job)
