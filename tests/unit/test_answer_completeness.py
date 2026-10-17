"""The final graph query's result entities are always reported (D087), fictional entities only."""

from medkg.qa.answer import ensure_reported
from tests.unit.test_review_regressions import Model, app


def test_complete_answers_are_unchanged():
    assert ensure_reported('Asterol and Brinex are listed.',['Asterol','Brinex'])==(
        'Asterol and Brinex are listed.',None)
    assert ensure_reported('anything',[])==('anything',None)


def test_missing_names_are_appended_once():
    text,done = ensure_reported('Asterol is indicated.',['Asterol','Brinex','Brinex',None])
    assert done=='appended' and text.endswith('Also recorded in the knowledge graph: Brinex.')


def test_an_answer_naming_no_result_is_replaced_by_the_results():
    text,done = ensure_reported('There are no drugs listed for this disease.',['Asterol','Brinex'])
    assert done=='replaced' and text.splitlines()[1:]==['- Asterol','- Brinex']


def test_name_matching_ignores_case_and_punctuation():
    assert ensure_reported('ASTEROL, brinex.',['Asterol','Brinex'])[1] is None


def test_a_name_inside_a_longer_reported_name_is_still_missing():
    text,done = ensure_reported('- late onset Orion fever',['late onset Orion fever','Orion fever'])
    assert done=='appended' and text.endswith('Also recorded in the knowledge graph: Orion fever.')
    assert ensure_reported('Orion fever; late onset Orion fever',['late onset Orion fever','Orion fever'])[1] is None


def test_pipeline_appends_what_the_model_left_out(monkeypatch):
    result = app(monkeypatch,Model(text='Asterol is recorded.')).ask('What is Asterol indicated for?')
    assert result['answer_completed']=='appended' and 'Brinex' in result['answer']


def test_count_answers_are_not_completed(monkeypatch):
    class CountStore:
        executed_statements = []

        def read(self,*args,**kwargs):
            return []

        def run_generated(self,statement,params):
            from medkg.graph.store import QueryResult
            return QueryResult([{'count':2,'sources':['fictional']}],statement)
    pipeline = app(monkeypatch,Model(text='Count: 2'))
    pipeline.store = CountStore()
    result = pipeline.ask('How many diseases is Asterol indicated for?')
    assert 'answer_completed' not in result and result['answer'].startswith('Count: 2')


def test_safety_refusal_is_not_overridden(monkeypatch):
    result = app(monkeypatch,Model(text='Take two tablets of Asterol daily.')).ask('What is Asterol indicated for?')
    assert result['refused'] and result['safety']=='dosage' and 'answer_completed' not in result
