"""Deterministic intersection templates (decision D082), using fictional entities only."""

import pytest
from pydantic import ValidationError

from medkg.config import Settings
from medkg.graph.guard import check
from medkg.graph.store import QueryResult
from medkg.qa.linker import Linker
from medkg.qa.pipeline import Pipeline
from medkg.qa.planner import Step
from medkg.qa.router import route, wants_shared
from medkg.retrieval import templates
from tests.unit.test_review_regressions import Model, span, trace

ENTITIES = [
    {'uid':'fiction:orion','label':'Disease','name':'Orion fever','synonyms':[]},
    {'uid':'fiction:lyra','label':'Disease','name':'Lyra disease','synonyms':[]},
    {'uid':'fiction:cold','label':'Disease','name':'common cold','synonyms':[]},
    {'uid':'fiction:asterol','label':'Drug','name':'Asterol','synonyms':[]},
    {'uid':'fiction:brinex','label':'Drug','name':'Brinex','synonyms':[]},
    {'uid':'fiction:amber','label':'Phenotype','name':'Amber spots','synonyms':[]},
]


@pytest.mark.parametrize('intent,count', [('drugs_for',False),('phenotypes',False),
                                          ('interactions',False),('drugs_for',True)])
def test_shared_query_passes_the_guard_and_excludes_anchors(intent,count):
    statement,params = templates.query(intent,['fiction:orion','fiction:lyra'],count=count,shared=True)
    assert check(statement).limit==25
    assert 'size(anchor_uids) = size($uids)' in statement and 'NOT b.uid IN $uids' in statement
    assert params=={'uids':['fiction:orion','fiction:lyra']}


def test_shared_query_needs_two_anchors():
    with pytest.raises(ValueError):
        templates.query('drugs_for',['fiction:orion'],shared=True)


@pytest.mark.parametrize('question,intent,shared',[
    ('Which drugs are indicated for both Orion fever and Lyra disease?','drugs_for',True),
    ('Which symptoms do Orion fever and Lyra disease have in common?','phenotypes',True),
    ('What clinical features are shared by Orion fever and Lyra disease?','phenotypes',True),
    ('How many drugs treat both Orion fever and Lyra disease?','drugs_for',True),
    ('Which drugs interact with both Asterol and Brinex?','interactions',True),
    ('Does Asterol interact with Brinex?','interactions',False),
    ('What are the symptoms of common cold?','phenotypes',False),
])
def test_intersections_route_to_templates(question,intent,shared):
    candidates = Linker(ENTITIES).in_question(question)
    assert route(question,candidates)==intent
    anchors = [c for c in candidates if c.label==templates.SPECS[intent][0]]
    assert wants_shared(question,anchors) is shared


@pytest.mark.parametrize('question',[
    'Which drugs are indicated for Orion fever but not contraindicated in Lyra disease?',
    'Which drugs treat both Orion fever and Amber spots?',
    'Which drugs treat Orion fever and Lyra disease?',
])
def test_exclusions_mixed_labels_and_plain_unions_stay_with_the_planner(question):
    assert route(question,Linker(ENTITIES).in_question(question)) is None


def test_planner_accepts_only_boolean_shared_flags():
    base = {'intent':'genes','uids':['fiction:orion','fiction:lyra']}
    assert Step(tool='template',args={**base,'shared':True}).args['shared'] is True
    assert Step(tool='template',args={**base,'shared':'true'}).args['shared'] is True
    for value in ('yes',2):
        with pytest.raises(ValidationError):
            Step(tool='template',args={**base,'shared':value})


class RecordingStore:
    def __init__(self):
        self.executed_statements,self.calls = [],[]

    def read(self,*args,**kwargs):
        return []

    def run_generated(self,statement,params):
        self.executed_statements.append(statement)
        self.calls.append((statement,params))
        return QueryResult([{'uid':'fiction:asterol','name':'Asterol','sources':['fictional'],
                             'anchor_uids':['fiction:orion','fiction:lyra']}],statement)


def test_pipeline_runs_the_intersection_template(monkeypatch):
    monkeypatch.setattr('medkg.qa.pipeline.request_trace',trace)
    monkeypatch.setattr('medkg.qa.pipeline.span',span)
    store = RecordingStore()
    pipeline = Pipeline(Settings(phase=3,cache=False,reasoning='plan'),store=store,llm=Model(),entities=ENTITIES)
    result = pipeline.ask('Which drugs are indicated for both Orion fever and Lyra disease?')
    statement,params = store.calls[0]
    assert result['route']=='template' and result['intent']=='drugs_for'
    assert 'size(anchor_uids) = size($uids)' in statement
    assert sorted(params['uids'])==['fiction:lyra','fiction:orion']
    assert 'Asterol' in result['answer']
