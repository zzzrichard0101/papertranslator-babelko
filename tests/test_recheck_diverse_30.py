import importlib
from pathlib import Path

from babelko.storage import read, save


def runner(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'scripts'))
    return importlib.import_module('recheck_diverse_30')


def test_recheck_resumes_only_unprocessed_cases(tmp_path, monkeypatch):
    module = runner(monkeypatch)
    base = tmp_path / 'corpus'
    (base / 'runs').mkdir(parents=True)
    save(base / 'manifest.json', {'cases': [{'key': 'a'}, {'key': 'b'}]})
    save(base / 'runs' / 'b.json', {'attempts': 1, 'status': 'partial'})
    plan_path = tmp_path / 'plan.json'
    save(plan_path, {'base': str(base), 'keys': ['a', 'b'], 'status': 'waiting',
                     'processed': {'a': {'attempts': 2, 'status': 'completed'}}})
    calls = []

    def fake_run(location, case_key):
        calls.append(case_key)
        save(base / 'runs' / 'b.json', {'attempts': 2, 'status': 'completed'})

    monkeypatch.setattr(module, 'run', fake_run)
    monkeypatch.setattr(module, 'summarize', lambda location: None)
    module.recheck(plan_path)
    assert calls == ['b']
    assert read(plan_path)['status'] == 'complete'
    assert read(plan_path)['processed']['b']['status'] == 'completed'


def test_recheck_waits_without_consuming_case_when_model_busy(tmp_path, monkeypatch):
    module = runner(monkeypatch)
    base = tmp_path / 'corpus'
    (base / 'runs').mkdir(parents=True)
    save(base / 'manifest.json', {'cases': [{'key': 'a'}]})
    plan_path = tmp_path / 'plan.json'
    save(plan_path, {'base': str(base), 'keys': ['a'], 'status': 'pending', 'processed': {}})
    monkeypatch.setattr(module, 'run', lambda location, case_key: None)
    module.recheck(plan_path)
    assert read(plan_path)['status'] == 'waiting'
    assert read(plan_path)['processed'] == {}
