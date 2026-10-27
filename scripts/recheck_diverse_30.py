"""Resume a frozen, selected corpus recheck from its local checkpoint plan."""

import argparse
import datetime as dt
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from babelko.storage import read, save
from diverse_30_corpus import run, summarize


TERMINAL = {'completed', 'partial', 'failed'}


def recheck(plan_path):
    plan_path = Path(plan_path).resolve()
    plan = read(plan_path)
    base = Path(plan['base']).resolve()
    cases = {row['key'] for row in read(base / 'manifest.json')['cases']}
    keys = plan['keys']
    if len(keys) != len(set(keys)) or not set(keys) <= cases:
        raise ValueError('Recheck plan contains unknown or duplicate cases')
    processed = plan.setdefault('processed', {})
    if not set(processed) <= set(keys):
        raise ValueError('Recheck plan contains unknown processed cases')
    if plan.get('status') == 'complete':
        return
    if (base / 'batch-hold.json').exists():
        plan['status'] = 'held'
        save(plan_path, plan)
        return

    plan['status'] = 'running'
    save(plan_path, plan)
    for key in keys:
        if key in processed:
            continue
        record_path = base / 'runs' / (key + '.json')
        before = read(record_path) if record_path.exists() else {}
        print(f'recheck {key}: attempt {before.get("attempts", 0) + 1}', flush=True)
        run(base, case_key=key)
        after = read(record_path) if record_path.exists() else {}
        if after.get('attempts', 0) <= before.get('attempts', 0) or after.get('status') not in TERMINAL:
            plan['status'] = 'waiting'
            save(plan_path, plan)
            print(f'recheck {key}: waiting for the next scheduled run', flush=True)
            return
        processed[key] = dict(attempts=after['attempts'], status=after['status'],
                              ended_at=after.get('ended_at'))
        save(plan_path, plan)
        print(f'recheck {key}: {after["status"]} ({len(processed)}/{len(keys)})', flush=True)
        # Stop an unproductive batch and preserve every job for diagnosis.
        recent = list(processed.values())[-3:]
        if len(recent) == 3 and all(row['status'] == 'failed' for row in recent):
            save(base / 'batch-hold.json', dict(reason='three consecutive recheck worker failures',
                                                 recent=list(processed)[-3:],
                                                 created_at=dt.datetime.now(dt.timezone.utc).isoformat()))
            plan['status'] = 'held'
            save(plan_path, plan)
            return
    summarize(base)
    plan['status'] = 'complete'
    plan['completed_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
    save(plan_path, plan)
    print('Selected corpus recheck complete.', flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--task-name', help='Windows scheduled task to disable after plan completion')
    args = parser.parse_args()
    log = args.plan.parent / 'recheck.log'
    with log.open('a', encoding='utf-8') as stream:
        with redirect_stdout(stream), redirect_stderr(stream):
            print('recheck start', dt.datetime.now(dt.timezone.utc).isoformat(), flush=True)
            try:
                recheck(args.plan)
                if args.task_name and read(args.plan).get('status') == 'complete':
                    subprocess.run(['schtasks','/Change','/TN',args.task_name,'/DISABLE'],
                                   check=True,capture_output=True,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
                    print('completed scheduled recheck disabled',flush=True)
            finally:
                print('recheck stop', dt.datetime.now(dt.timezone.utc).isoformat(), flush=True)


if __name__ == '__main__':
    main()
