"""Same-name Disease/Phenotype readings and reverse side-effect lookup (fictional data)."""

import pytest

from medkg.config import Settings
from medkg.graph.store import QueryResult
from medkg.qa.linker import Linker
from medkg.qa.pipeline import Pipeline
from medkg.qa.planner import graph_fallback_allowed
from medkg.qa.router import requested_target, route
from medkg.retrieval import templates
from tests.unit.test_review_regressions import Model, span, trace

ENTITIES = [
    {'uid':'fiction:orion-disease','label':'Disease','name':'Orion fever','synonyms':[]},
    {'uid':'fiction:orion-phenotype','label':'Phenotype','name':'Orion fever','synonyms':[]},
    {'uid':'fiction:drug-a','label':'Drug','name':'Asterol','synonyms':[]},
    {'uid':'fiction:phenotype-a','label':'Phenotype','name':'Amber spots','synonyms':[]},
    {'uid':'fiction:vela-1','label':'Disease','name':'Vela syndrome','synonyms':[]},
    {'uid':'fiction:vela-2','label':'Disease','name':'Vela syndrome','synonyms':[]},
]


@pytest.mark.parametrize('question,intent',[
    ('What are the symptoms of Orion fever?','phenotypes'),
    ('Which diseases have Orion fever as a symptom?','diseases_for'),
    ('Which drugs are indicated for Orion fever?','drugs_for'),
    ('Let me know which drugs are indicated for Orion fever.','drugs_for'),
    ('Which drugs have Amber spots as a side effect?','drugs_with_side_effect'),
    ('What drugs cause Amber spots?','drugs_with_side_effect'),
])
def test_relation_selects_the_reading_of_a_same_name_pair(question,intent):
    candidates,unresolved = Linker(ENTITIES).question_mentions(question)
    assert not unresolved
    assert route(question,candidates)==intent


def test_same_label_duplicates_stay_ambiguous():
    linker = Linker(ENTITIES)
    question = 'Which drugs are indicated for Vela syndrome?'
    candidates = linker.in_question(question)
    assert route(question,candidates) is None
    assert not graph_fallback_allowed('Which genes are associated with Vela syndrome?',
                                      linker.describe(candidates))


def test_cross_label_pair_may_use_guarded_graph_fallback():
    linker = Linker(ENTITIES)
    question = 'Which genes are associated with Orion fever?'
    assert graph_fallback_allowed(question,linker.describe(linker.in_question(question)))


@pytest.mark.parametrize('question,label',[
    ('Which diseases have it?','Disease'),('What are the symptoms of it?','Phenotype'),
    ('What drugs cause it?','Drug'),('Which side effects does it have?','Phenotype'),
    ('Tell me about it.',None),
])
def test_requested_target(question,label):
    assert requested_target(question)==label


def test_reverse_side_effect_template_shape():
    statement,params = templates.query('drugs_with_side_effect',['fiction:phenotype-a'])
    assert '(a:Phenotype)<-[r:HAS_SIDE_EFFECT]-(b:Drug)' in statement
    assert params['uid']=='fiction:phenotype-a'


class RecordingStore:
    def __init__(self):
        self.executed_statements,self.params = [],[]

    def read(self,*args,**kwargs):
        return []

    def run_generated(self,statement,params):
        self.executed_statements.append(statement)
        self.params.append(params)
        return QueryResult([{'uid':'fiction:drug-a','name':'Asterol','source':'fictional'}],statement)


class EmptyGraphStore(RecordingStore):
    def run_generated(self,statement,params):
        self.executed_statements.append(statement)
        return QueryResult([],statement)


def test_empty_template_falls_back_to_documents_about_the_anchor(monkeypatch):
    monkeypatch.setattr('medkg.qa.pipeline.request_trace',trace)
    monkeypatch.setattr('medkg.qa.pipeline.span',span)
    pipeline = Pipeline(Settings(phase=3,cache=False),store=EmptyGraphStore(),llm=Model(),entities=ENTITIES)
    calls = []

    def text_tool(name,args):
        calls.append((name,args))
        return QueryResult([{'uid':'chunk:orion','name':'Orion fever summary','source':'medlineplus',
                             'text':'Orion fever causes Amber spots.'}],'')
    monkeypatch.setattr(pipeline,'_hybrid_tool',text_tool)
    result = pipeline.ask('What are the symptoms of Orion fever?')
    assert calls==[('vector_search',{'query':'What are the symptoms of Orion fever?',
                                      'uids':['fiction:orion-disease']})]
    assert result['retrieval_fallback']=='vector_search' and result['response_status']=='answered'
    phase1 = Pipeline(Settings(phase=1,cache=False),store=EmptyGraphStore(),llm=Model(),entities=ENTITIES)
    assert phase1.ask('What are the symptoms of Orion fever?')['response_status']=='unsupported'


def test_pipeline_queries_the_disease_reading_and_keeps_it_as_focus(monkeypatch):
    monkeypatch.setattr('medkg.qa.pipeline.request_trace',trace)
    monkeypatch.setattr('medkg.qa.pipeline.span',span)
    store = RecordingStore()
    pipeline = Pipeline(Settings(phase=3,cache=False),store=store,llm=Model(),entities=ENTITIES)
    result = pipeline.ask('Which drugs are indicated for Orion fever?')
    assert result['route']=='template' and result['intent']=='drugs_for'
    assert store.params[0]['uid']=='fiction:orion-disease'
    assert result['focus']==['Orion fever'] and 'Asterol' in result['answer']
