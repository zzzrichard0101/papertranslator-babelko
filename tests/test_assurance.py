import json
import pytest
from babelko.assurance import view,segments,tasks,validate,accepted,audit,REVISION,fingerprint


def reply(values,schema):
    return json.dumps([[v[k] for k in ['id','verdict','evidence','reason']] for v in values] if schema['items']['type']=='array' else values)


def test_segments_cover_tails_long_sentences_conditions_and_formulas():
    text="Dr. Smith uses 0.25 units; unless it rains, keep {v1}. "+('long phrase '*90)+" FINAL EXCEPTION"
    parts=segments(text)
    assert ''.join(''.join(parts).split())==''.join(view(text).split())
    assert any(p.startswith('unless') for p in parts) and parts[-1].endswith('FINAL EXCEPTION')
    assert parts[0].startswith('Dr. Smith')


def test_audit_cannot_pass_an_omitted_clause_with_no_literal_evidence():
    batch=tasks('Use the device only if dry.','장치를 사용한다.')[:1]
    with pytest.raises(ValueError):validate(batch,[dict(id='s0',verdict='faithful',evidence=[],reason='')],batch[0]['text'],'장치를 사용한다.')
    with pytest.raises(ValueError):validate(batch,[dict(id='s0',verdict='faithful',evidence=['t99'],reason='')],batch[0]['text'],'장치를 사용한다.')
    with pytest.raises(ValueError):validate(batch,[dict(id='s0',verdict='faithful',evidence=['s0'],reason='')],batch[0]['text'],'장치를 사용한다.')


def test_ids_duplicates_and_added_target_claims_are_checked():
    batch=tasks('Use the device.','장치를 사용한다. 수명은 무한하다.')
    wrong=[dict(id=batch[0]['id'],verdict='faithful',evidence=['t0'],reason='') for _ in batch]
    with pytest.raises(ValueError):validate(batch,wrong,'Use the device.','장치를 사용한다. 수명은 무한하다.')
    result=validate(batch,[dict(id='s0',verdict='faithful',evidence=['t0'],reason=''),
        dict(id='t0',verdict='faithful',evidence=['s0'],reason=''),
        dict(id='t1',verdict='unsupported',evidence=[],reason='No lifetime claim in source')],
        'Use the device.','장치를 사용한다. 수명은 무한하다.')
    assert result[-1]['verdict']=='unsupported'


def test_cached_assurance_is_bound_to_both_texts_and_context():
    r=dict(source='Use it.',final='사용한다.',context='')
    checks=[dict(id='s0',verdict='faithful',evidence=['t0'],reason=''),dict(id='t0',verdict='faithful',evidence=['s0'],reason='')]
    r['assurance']=dict(revision=REVISION,fingerprint=fingerprint(r),checks=checks)
    assert accepted(r)
    r['final']='사용하지 않는다.'
    assert not accepted(r)


def test_auditor_retries_invalid_quotes_and_cancellation_never_passes():
    r=dict(source='Do not stop.',final='멈추지 않는다.',context='')
    replies=iter([json.dumps([['s0','faithful',['t99'],''],['t0','faithful',['s0'],'']]),
        json.dumps([dict(id='s0',verdict='faithful',evidence=['t0'],reason=''),dict(id='t0',verdict='faithful',evidence=['s0'],reason='')])])
    r['assurance']=audit(r,lambda *_:next(replies))
    assert accepted(r)
    assert r['assurance']['checks'][0]['quoted_spans'][0]['text']=='멈추지 않는다.'
    with pytest.raises(InterruptedError):audit(r,lambda *_:pytest.fail('request after cancellation'),lambda:True)


def test_grouped_audit_requires_every_clause_and_own_record_evidence():
    from babelko.assurance import audit_many
    records=[dict(source='Use it.',final='사용한다.',context=''),dict(source='Do not use it.',final='사용한다.',context='')]
    calls=[]
    def request(messages,schema):
        data=json.loads(messages[1]['content']);calls.append(data)
        return reply([dict(id=x['id'],verdict='faithful' if x['record_id']==0 else 'contradiction',
            evidence=[v['id'] for v in data['UNITS'] if v['record_id']==x['record_id'] and v['side']!=x['side']],
            reason='' if x['record_id']==0 else 'Negation missing') for x in data['UNITS'] if x['id'] in data['CHECK_IDS']],schema)
    results=audit_many(records,request)
    assert len(calls)==1
    for r,result in zip(records,results):r['assurance']=result
    assert accepted(records[0]) and not accepted(records[1])
    assert results[1]['checks'][0]['quoted_spans'][0]['text']=='사용한다.'
    def cross_record(messages,schema):
        data=json.loads(messages[1]['content'])
        return reply([dict(id=x['id'],verdict='faithful',evidence=[v['id'] for v in data['UNITS'] if v['record_id']!=x['record_id'] and v['side']!=x['side']],reason='') for x in data['UNITS'] if x['id'] in data['CHECK_IDS']],schema)
    with pytest.raises(ValueError,match='다른 문단'):audit_many(records,cross_record)


def test_adaptive_batch_reduces_calls_and_falls_back_without_dropping_checks():
    r=dict(source=' '.join('Sentence '+str(i)+'.' for i in range(8)),final=' '.join('문장 '+str(i)+'.' for i in range(8)),context='')
    calls=[]
    def request(messages,schema):
        data=json.loads(messages[1]['content']);calls.append(len(data['CHECK_IDS']))
        if len(data['CHECK_IDS'])>6:raise ValueError('injected truncated response')
        return json.dumps([dict(id=x['id'],verdict='faithful',evidence=[v['id'] for v in data['UNITS'] if v['side']!=x['side']],reason='') for x in data['UNITS'] if x['id'] in data['CHECK_IDS']])
    result=audit(r,request);r['assurance']=result
    assert calls==[16,6,6,4] and len(result['checks'])==16 and accepted(r)


def test_known_defect_evidence_is_current_but_never_accepted():
    from babelko.assurance import checked
    r=dict(source='Do not stop.',final='멈춘다.',context='')
    r['assurance']=dict(revision=REVISION,fingerprint=fingerprint(r),checks=[dict(id='s0',verdict='contradiction',evidence=['t0'],reason='negation'),dict(id='t0',verdict='contradiction',evidence=['s0'],reason='negation')])
    assert checked(r) and not accepted(r)
    r['final']='멈추지 않는다.'
    assert checked(r) is None


def test_fragment_keeps_classic_protocol_and_compact_result_rejects_missing_checks():
    from babelko.assurance import isolated,decode
    r=dict(source='Recent studies improved the distribution of',final='최근 연구들은 분포를 개선했다.',context='')
    assert isolated(r)
    def request(messages,schema):
        data=json.loads(messages[1]['content'])
        assert 'record_id' not in data['UNITS'][0] and schema['items']['type']=='object' and len(messages)==2
        return json.dumps([dict(id=x['id'],verdict='faithful',evidence=['t0'] if x['side']=='source' else ['s0'],reason='') for x in data['UNITS']])
    r['assurance']=audit(r,request);assert accepted(r)
    with pytest.raises(ValueError):decode([['s0','faithful',['t0']]],True)
    with pytest.raises(ValueError):validate(tasks('Use it.','사용한다.'),decode([['s0','faithful',['t0'],'']],True),'Use it.','사용한다.')


def test_dense_long_units_keep_classic_coverage_instead_of_large_batch_approval():
    from babelko.assurance import isolated
    r=dict(source=' '.join('Sentence '+str(i)+'.' for i in range(10)),final=' '.join('문장 '+str(i)+'.' for i in range(10)),context='')
    assert isolated(r);calls=[]
    def request(messages,schema):
        data=json.loads(messages[1]['content']);calls.append(len(data['CHECK_IDS']))
        assert schema['items']['type']=='object' and len(messages)==2
        return json.dumps([dict(id=x['id'],verdict='faithful',evidence=[v['id'] for v in data['UNITS'] if v['side']!=x['side']],reason='') for x in data['UNITS'] if x['id'] in data['CHECK_IDS']])
    r['assurance']=audit(r,request)
    assert calls==[6,6,6,2] and accepted(r)
