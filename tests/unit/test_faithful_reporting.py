"""Generated-query descriptions, the faithful-reporting rule and relation phrasing (D086), fictional entities only."""

import json

import pytest

from medkg.config import Settings
from medkg.graph.store import QueryResult
from medkg.qa.answer import PROMPT
from medkg.qa.linker import Linker
from medkg.qa.pipeline import Pipeline
from medkg.qa.router import route
from medkg.retrieval import text2cypher
from tests.unit.test_explicit_evidence import RecordingModel, evidence
from tests.unit.test_review_regressions import span, trace

ENTITIES = [
    {'uid':'fiction:asterol','label':'Drug','name':'Asterol','synonyms':[]},
    {'uid':'fiction:orion','label':'Disease','name':'Orion fever','synonyms':[]},
    {'uid':'fiction:amber','label':'Phenotype','name':'Amber spots','synonyms':[]},
]


@pytest.mark.parametrize('question,intent',[
    ('What genes are linked to Orion fever?','genes'),
    ('What adverse effects are reported for Asterol?','side_effects'),
    ('What conditions can present with Amber spots?','diseases_for'),
])
def test_relation_phrasing_is_not_an_unresolved_name(question,intent):
    candidates,unresolved = Linker(ENTITIES).question_mentions(question)
    assert not unresolved and route(question,candidates)==intent


def test_unknown_names_are_still_unresolved():
    _,unresolved = Linker(ENTITIES).question_mentions('Which drugs interact with Zorvaxa?')
    assert unresolved==['zorvaxa']


def test_prompt_forbids_denying_returned_rows():
    assert 'never state that nothing was found' in PROMPT and 'outside knowledge' in PROMPT


class EmptyStore:
    executed_statements = []

    def read(self,*args,**kwargs):
        return []


def test_generated_query_rows_are_described_as_the_answer(monkeypatch):
    monkeypatch.setattr('medkg.qa.pipeline.request_trace',trace)
    monkeypatch.setattr('medkg.qa.pipeline.span',span)
    statement = 'MATCH (d:Disease {uid:$d})<-[:INDICATED_FOR]-(x:Drug) RETURN x.uid AS uid, x.name AS name LIMIT 25'
    generated = QueryResult([{'uid':'fiction:asterol','name':'Asterol'}],statement)
    generated.params = {'d':'fiction:orion'}
    monkeypatch.setattr('medkg.qa.pipeline.text2cypher.retrieve',lambda *args: generated)
    model = RecordingModel()
    model.plan = {'steps':[{'tool':'text2cypher','args':{'question':'Which drugs are indicated for Orion fever but not in Asterol trials?'}}]}
    pipeline = Pipeline(Settings(phase=3,cache=False,reasoning='plan'),store=EmptyStore(),llm=model,entities=ENTITIES)
    result = pipeline.ask('Which drugs are indicated for Orion fever but not in Asterol trials?')
    assert result['route']=='planner'
    query = evidence(model.prompts[0])['executed_graph_queries'][0]
    assert query['description']==text2cypher.describe('Which drugs are indicated for Orion fever but not in Asterol trials?')
    assert 'Each row is one entity that satisfies all of its constraints' in query['description']
    assert json.dumps(query['params'])=='{"d": "fiction:orion"}'
