"""Progress events for the star map (D128), fictional entities only."""

from medkg.qa import events
from tests.unit.test_reasoning_chain import QUESTION, Script, step
from tests.unit.test_review_regressions import Model, app, both


def collect(pipeline, question):
    seen = []
    result = pipeline.ask(question, events=lambda kind, data: seen.append((kind, data)))
    return result, seen


def test_a_plan_reports_its_entities_each_step_and_the_writing(monkeypatch):
    pipeline = app(monkeypatch, Model(text='Asterol and Brinex are recorded.', plan=both('indications')))
    result, seen = collect(pipeline, 'What are Asterol and Brinex indicated for?')
    kinds = [k for k, _ in seen]
    assert kinds == ['linked', 'step', 'writing'] and result['response_status'] == 'answered'
    linked, found = seen[0][1], seen[1][1]
    assert linked['route'] == 'planner'
    assert [e['uid'] for e in linked['entities']] == ['fiction:drug-a', 'fiction:drug-b']
    assert found['kind'] == 'graph' and found['sources'] == ['fiction:drug-a', 'fiction:drug-b']
    assert found['description'].startswith('The rows are') and found['found'] == 2
    assert [r['name'] for r in found['results']] == ['Asterol', 'Brinex'] and found['within'] == []


def test_a_chain_reports_each_lookup_and_the_observations_it_used(monkeypatch):
    model = Script(step('relation', intent='interactions', uids=['fiction:drug-a']),
                   step('relation', intent='side_effects', uids=['$1']),
                   'Amber spots is recorded.')
    pipeline = app(monkeypatch, model)
    pipeline.settings.reasoning = 'chain'
    _, seen = collect(pipeline, QUESTION)
    steps = [d for k, d in seen if k == 'step']
    assert [k for k, _ in seen].count('thinking') == 3
    assert steps[0]['sources'] == ['fiction:drug-a'] and steps[0]['within'] == []
    # "$1" is the first observation's entities: no uid of its own, the observation it used.
    assert steps[1]['sources'] == [] and steps[1]['within'] == [1]
    assert {r['name'] for r in steps[1]['results']} == {'Amber spots', 'Indigo spots'}


def test_a_failing_callback_never_reaches_the_answer(monkeypatch):
    def broken(kind, data):
        raise RuntimeError('page went away')
    pipeline = app(monkeypatch, Model(text='Asterol and Brinex are recorded.', plan=both('indications')))
    result = pipeline.ask('What are Asterol and Brinex indicated for?', events=broken)
    assert result['response_status'] == 'answered' and pipeline.events is None


def test_entity_rows_leave_out_text_and_repeats():
    rows = [{'uid': 'fiction:drug-a', 'name': 'Asterol'}, {'uid': 'fiction:drug-a', 'name': 'Asterol'},
            {'uid': 'chunk:1', 'name': 'Leaflet', 'text': 'a passage'}, {'uid': 'fiction:x'}, {'count': 3}]
    assert events.entity_rows(rows) == [{'uid': 'fiction:drug-a', 'name': 'Asterol'}]
    assert events.plan_refs({'uids': '$step2', 'other': ['$step1']}) == [2, 1]
