import json

from medkg import tracing
from medkg.qa.answer import finalize
from medkg.qa.planner import Plan
from medkg.qa.safety import english, output_violation


def test_actual_sdk_parent_spans_and_metadata_only(tmp_path,monkeypatch):
    monkeypatch.delenv('OTEL_EXPORTER_OTLP_ENDPOINT',raising=False)
    monkeypatch.setattr(tracing,'ROOT',tmp_path)
    monkeypatch.setattr(tracing,'_PROVIDER',None)
    with tracing.request_trace() as trace_id:
        with tracing.span('routing',route='template'):
            with tracing.span('tool.template',rows=2):
                pass
        with tracing.span('request.result',route='template',prompt_tokens=10,completion_tokens=2):
            pass
    records = [json.loads(line) for file in (tmp_path/'runs/traces').glob('*.jsonl')
               for line in file.read_text().splitlines()]
    by_name = {r['name']:r for r in records}
    assert {r['trace_id'] for r in records}=={trace_id}
    assert len(trace_id)==32 and by_name['ask']['parent_span_id'] is None
    assert by_name['routing']['parent_span_id']==by_name['ask']['span_id']
    assert by_name['tool.template']['parent_span_id']==by_name['routing']['span_id']
    assert by_name['ask']['attributes']['prompt_tokens']==10
    assert all('question' not in r['attributes'] and r['seconds']>=0 for r in records)
    tracing.provider().shutdown()


def test_both_conflicting_claims_are_added_by_code():
    rows = [{'subject':'Fictional A','object':'Fictional B','relation':relation,'source':source,
             'conflict':True} for relation,source in [('INDICATED_FOR','fixture-original'),
                                                     ('CONTRAINDICATED_FOR','fixture-extracted')]]
    result = finalize('Recorded associations.',rows,False)
    assert 'INDICATED_FOR Fictional B [fixture-original]' in result
    assert 'CONTRAINDICATED_FOR Fictional B [fixture-extracted]' in result


def test_conservative_output_safety_and_language_guard():
    assert output_violation('Take 20 mg daily.').category=='dosage'
    assert output_violation('You have a fictional illness.').category=='diagnosis_request'
    assert output_violation('This is a reported association, not a diagnosis.') is None
    assert not english('Quels médicaments sont indiqués?')
    assert english('What does the café discussion say about fictional A?')
    plan = Plan.model_validate({'steps':[{'tool':'vector_search',
        'args':{'query':'fictional topic','source':None,'uids':None}}]})
    assert plan.steps[0].args=={'query':'fictional topic'}
