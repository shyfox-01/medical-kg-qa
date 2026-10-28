"""Name mapping and query descriptions in the answer evidence (D085), fictional entities only."""

import json

import pytest

from medkg.config import Settings
from medkg.graph.store import QueryResult
from medkg.qa.answer import messages
from medkg.qa.pipeline import Pipeline
from medkg.retrieval import templates
from tests.unit.test_review_regressions import Model, span, trace

ENTITIES = [
    {'uid':'fiction:asterol','label':'Drug','name':'Asterol','synonyms':['Brandex']},
    {'uid':'fiction:orion','label':'Disease','name':'Orion fever','synonyms':[]},
    {'uid':'fiction:lyra','label':'Disease','name':'Lyra disease','synonyms':[]},
]


def evidence(message_list):
    return json.loads(message_list[1]['content'].split('<evidence>')[1].split('</evidence>')[0])


@pytest.mark.parametrize('intent',sorted(templates.SPECS))
def test_every_template_has_a_description(intent):
    text = templates.describe(intent,['Orion fever'])
    assert text.startswith('The rows are ') and 'Orion fever' in text and text.endswith('.')


def test_descriptions_state_shared_counted_and_pairwise_meaning():
    shared = templates.describe('drugs_for',['Orion fever','Lyra disease'],shared=True)
    assert 'every one of Orion fever and Lyra disease' in shared and 'linked to all of them' in shared
    assert 'any of Orion fever and Lyra disease' in templates.describe('drugs_for',['Orion fever','Lyra disease'])
    assert templates.describe('drugs_for',['Orion fever'],count=True).startswith('The rows give the number of drugs')
    assert 'interaction between Asterol and Brinex' in templates.describe('interactions',['Asterol','Brinex'])
    assert '4 entities retrieved by an earlier step' in templates.describe('genes',['a','b','c','d'])


def test_question_entities_appear_only_when_given():
    assert 'question_entities' not in evidence(messages('Fictional?',[{'name':'Asterol'}]))
    mapping = [{'mention':'Brandex','entity':'Asterol','uid':'fiction:asterol','type':'Drug'}]
    assert evidence(messages('Fictional?',[{'name':'Asterol'}],entities=mapping))['question_entities']==mapping


class RecordingModel(Model):
    def __init__(self):
        super().__init__()
        self.prompts = []

    def chat(self,message_list,*args):
        self.prompts.append(message_list)
        return super().chat(message_list,*args)


class IndicationStore:
    def __init__(self):
        self.executed_statements = []

    def read(self,*args,**kwargs):
        return []

    def run_generated(self,statement,params):
        self.executed_statements.append(statement)
        return QueryResult([{'uid':'fiction:orion','name':'Orion fever','source':'fictional',
                             'anchor_uid':'fiction:asterol','anchor_name':'Asterol'}],statement)


def test_brand_name_list_names_the_brand_and_the_entity_it_was_read_as(monkeypatch):
    # A list about one entity is stated in code (D124); the brand is shown with its entity.
    monkeypatch.setattr('medkg.qa.pipeline.request_trace',trace)
    monkeypatch.setattr('medkg.qa.pipeline.span',span)
    model = RecordingModel()
    pipeline = Pipeline(Settings(phase=3,cache=False),store=IndicationStore(),llm=model,entities=ENTITIES)
    result = pipeline.ask('What is Brandex prescribed to treat?')
    assert result['route']=='template' and result['intent']=='indications'
    assert not model.prompts
    assert result['answer'].startswith('The knowledge graph records 1 disease for which Brandex (Asterol) is '
                                       'indicated:\n- Orion fever')
    assert result['queries'][0]['description']=='The rows are diseases for which Asterol is indicated.'
