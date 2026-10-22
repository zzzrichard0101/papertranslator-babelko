from unittest.mock import patch
import pytest
from babelko.performance import StateWriter,Performance
from babelko.storage import read


def test_progress_throttling_keeps_failure_and_completion_durable(tmp_path):
    writer=StateWriter(tmp_path/'state.json')
    with patch('babelko.performance.time.monotonic',return_value=100):
        assert writer.write(dict(status='translating',progress=1))
        assert not writer.write(dict(status='translating',progress=2))
        assert writer.write(dict(status='failed',error='defect',progress=2))
        assert read(tmp_path/'state.json')['error']=='defect'
        assert writer.write(dict(status='completed',progress=100))
        assert writer.write(dict(status='completed',progress=100),force=True)


def test_component_and_request_metrics_survive_failure(tmp_path):
    performance=Performance(tmp_path)
    with pytest.raises(ValueError),performance.measure('test.component'):raise ValueError('defect')
    performance.add('tokens.prompt',count=42);performance.flush()
    row=read(tmp_path/'performance.json')
    assert row['counts']['tokens.prompt']==42 and row['counts']['test.component']==1


def test_checkpoint_skips_only_successfully_saved_identical_payloads(tmp_path):
    from babelko.hybrid import HybridTranslator
    t=object.__new__(HybridTranslator);t.checkpoints=tmp_path;t.stats={};record=dict(key='one',source='Original',final='번역')
    t.checkpoint(record);before=(tmp_path/'one.json').stat().st_mtime_ns
    t.checkpoint(record)
    assert (tmp_path/'one.json').stat().st_mtime_ns==before and t.stats['checkpoint_writes_avoided']==1
    record['final']='다른 번역'
    with patch('babelko.hybrid.save',side_effect=OSError('disk failure')):
        with pytest.raises(OSError):t.checkpoint(record)
    t.checkpoint(record);assert read(tmp_path/'one.json')['final']=='다른 번역'
