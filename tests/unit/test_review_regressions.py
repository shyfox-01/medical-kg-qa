"""Regression cases from the implementation review, using fictional data only."""

import copy
import json
import sys
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from eval import rescore
from eval.run import evaluate_case
from eval.score import Vocabulary, count_value, forbidden_content, score
from medkg.config import Settings
from medkg.graph.guard import CypherRejected, check
from medkg.graph.store import GraphStore, QueryResult
from medkg.ingest.extract import Relation, cached_edge_supported, extract
from medkg.ingest.openfda import parse
from medkg.qa.linker import Linker
from medkg.qa.pipeline import Pipeline
from medkg.qa.router import route
from medkg.qa.safety import assess, output_violation

ENTITIES = [
    {'uid':'fiction:drug-a','label':'Drug','name':'Asterol','synonyms':[]},
    {'uid':'fiction:drug-b','label':'Drug','name':'Brinex','synonyms':[]},
    {'uid':'fiction:disease','label':'Disease','name':'Orion syndrome','synonyms':[]},
    {'uid':'fiction:phenotype-a','label':'Phenotype','name':'Amber spots','synonyms':[]},
    {'uid':'fiction:phenotype-b','label':'Phenotype','name':'Indigo spots','synonyms':[]},
]


@contextmanager
def trace(*args,**kwargs):
    yield '0'*32


@contextmanager
def span(*args,**kwargs):
    yield {}


class Model:
    def __init__(self,text=None,plan=None):
        self.usage = {'calls':0,'prompt_tokens':0,'completion_tokens':0}
        self.text,self.plan = text,plan

    def chat_json(self,messages,*args):
        self.usage['calls'] += 1
        return self.plan

    def chat(self,messages,*args):
        self.usage['calls'] += 1
        if self.text is not None:
            return self.text
        rows = json.loads(messages[1]['content'].split('<evidence>')[1].split('</evidence>')[0])['rows']
        return '\n'.join(r['name'] for r in rows)


class Store:
    def __init__(self):
        self.executed_statements = []

    def read(self,*args,**kwargs):
        return []

    def run_generated(self,statement,params):
        self.executed_statements.append(statement)
        if 'HAS_SIDE_EFFECT' in statement:
            ids = params.get('uids',[params['uid']])
            rows = [dict(ENTITIES[3+i],anchor_uid=uid,source='fictional')
                    for i,uid in enumerate(['fiction:drug-a','fiction:drug-b']) if uid in ids]
        else:
            rows = [dict(e,source='fictional') for e in ENTITIES[:2]]
        return QueryResult(rows,statement)


def app(monkeypatch,model):
    monkeypatch.setattr('medkg.qa.pipeline.request_trace',trace)
    monkeypatch.setattr('medkg.qa.pipeline.span',span)
    return Pipeline(Settings(phase=3,cache=False),store=Store(),llm=model,entities=copy.deepcopy(ENTITIES))


@pytest.mark.parametrize('quantity',['two','2','half a','quarter of a','one and a half','twenty-one'])
def test_dose_words_are_blocked_before_any_provider_call(monkeypatch,quantity):
    model = Model()
    result = app(monkeypatch,model).ask(f'Can I take {quantity} tablets of Asterol?')
    assert result['refused'] and result['safety']=='dosage'
    assert model.usage['calls']==0


@pytest.mark.parametrize('instruction',[
    'Take two tablets of Asterol daily.', 'Take Asterol twice a day.',
    'Administer one capsule every six hours.', 'Use half a tablet at bedtime.',
])
def test_final_output_rejects_worded_doses_and_frequencies(monkeypatch,instruction):
    result = app(monkeypatch,Model(text=instruction)).ask('What is Asterol indicated for?')
    assert result['refused'] and result['safety']=='dosage'
    assert instruction not in result['answer']
    assert output_violation(instruction) is not None
    assert forbidden_content(instruction)


def test_graph_counts_are_not_medication_instructions():
    body = 'Count: 2. Two drugs and one phenotype are recorded.'
    assert not assess(body).blocked
    assert output_violation(body) is None and not forbidden_content(body)


@pytest.mark.parametrize('reverse',[False,True])
def test_combination_ingredients_keep_distinct_identities(reverse):
    nodes = copy.deepcopy(ENTITIES)
    label = {'id':'combo','openfda':{'generic_name':['Asterol and Brinex'],
             'substance_name':['ASTEROL','BRINEX'],'brand_name':['ComboBrand']},
             'description':['Fictional combination label.']}
    records = [{'drug_uid':e['uid'],'results':[label]} for e in nodes[:2]]
    documents,chunks,stats = parse(records[::-1] if reverse else records,nodes,'2026-10-05')
    assert len(documents)==1 and documents[0]['about']==['fiction:drug-a','fiction:drug-b']
    assert chunks[0]['about']==documents[0]['about']
    linker = Linker(nodes)
    for name,uid in [('Asterol','fiction:drug-a'),('Brinex','fiction:drug-b')]:
        candidates = linker.link(name,'Drug')
        assert len(candidates)==1 and candidates[0].uid==uid and not candidates[0].ambiguous
    assert not linker.link('ComboBrand','Drug')
    assert stats['quarantined_aliases']>0


def test_shared_brand_is_quarantined_and_single_ingredient_brand_is_linked():
    nodes = copy.deepcopy(ENTITIES)
    records = [{'drug_uid':e['uid'],'results':[{'id':str(i),
        'openfda':{'generic_name':[e['name']],'brand_name':['SharedBrand',f'UniqueBrand{i}']}}]}
        for i,e in enumerate(nodes[:2])]
    parse(records,nodes,'2026-10-05')
    linker = Linker(nodes)
    assert 'sharedbrand' not in linker.aliases
    assert linker.link('UniqueBrand1','Drug')[0].uid=='fiction:drug-b'


@pytest.mark.parametrize('question',[
    'Which drugs target genes associated with Orion syndrome?',
    'Which diseases are associated with genes targeted by Asterol?',
    'Which drugs for Orion syndrome and which genes are associated with it?',
    'What side effects are recorded for Asterol and Brinex?',
])
def test_compound_questions_go_to_planning(question):
    candidates = Linker(ENTITIES).in_question(question)
    assert route(question,candidates) is None


def test_single_relation_and_pair_interaction_templates_remain_available():
    linker = Linker(ENTITIES)
    assert route('Which drugs for Orion syndrome?',linker.in_question('Orion syndrome'))=='drugs_for'
    assert route('Does Asterol interact with Brinex?',linker.in_question('Asterol Brinex'))=='interactions'
    assert route('What about Orion syndrome?',linker.in_question('Orion syndrome'),'side_effects') is None


def test_anchor_mask_does_not_remove_relation_words_containing_its_name():
    linker = Linker([{'uid':'fiction:gene-name','name':'Gene','label':'Disease','synonyms':[]}])
    question = 'Which drugs target genes associated with Gene?'
    assert route(question,linker.in_question(question)) is None


def test_step_result_collection_retrieves_every_anchor(monkeypatch):
    plan = {'steps':[
        {'tool':'template','args':{'intent':'drugs_for','uids':['fiction:disease']}},
        {'tool':'template','args':{'intent':'side_effects','uids':'$step1'}},
    ]}
    result = app(monkeypatch,Model(plan=plan)).ask('Explain the drugs and their side effects for Orion syndrome.')
    assert result['failure_stage'] is None
    assert 'Amber spots' in result['answer'] and 'Indigo spots' in result['answer']
    rows = [r for r in result['contexts'] if r.get('anchor_uid')]
    assert {r['anchor_uid'] for r in rows}=={'fiction:drug-a','fiction:drug-b'}


@pytest.mark.parametrize('statement',[
    'RETURN 1 AS uid LIMIT 200 UNION ALL RETURN 2 AS uid LIMIT 200',
    'RETURN 1 AS uid UNION RETURN 2 AS uid',
    'CALL { RETURN 1 AS uid UNION ALL RETURN 2 AS uid } RETURN uid',
])
def test_union_is_rejected_before_execution(statement):
    with pytest.raises(CypherRejected,match='UNION'):
        check(statement)
    assert check("RETURN 'UNION ALL' AS name").limit==25


def test_driver_result_consumption_is_bounded_even_if_server_overproduces():
    class Cursor:
        index = 0
        def __iter__(self):
            return self
        def __next__(self):
            self.index += 1
            return SimpleNamespace(data=lambda:{'uid':self.index})
        def peek(self):
            return {'uid':self.index+1}
    cursor = Cursor()
    graph = GraphStore.__new__(GraphStore)
    graph.settings = Settings(max_limit=5)
    graph.executed_statements = []
    graph.driver = MagicMock()
    tx = graph.driver.session.return_value.__enter__.return_value.begin_transaction.return_value.__enter__.return_value
    tx.run.side_effect = [SimpleNamespace(consume=lambda:SimpleNamespace(notifications=[])),cursor]
    result = graph.run_generated('RETURN 1 AS uid LIMIT 999')
    assert len(result.rows)==5 and result.truncated and cursor.index==5


def test_cached_assertion_requires_current_catalog_support_for_both_endpoints():
    entities = {e['uid']:e for e in ENTITIES}
    text = 'Asterol is contraindicated for Orion syndrome.'
    edge = {'a':'fiction:drug-a','b':'fiction:disease','type':'CONTRAINDICATED_FOR','quote':text}
    assert cached_edge_supported(edge,{'text':text},entities)
    edge['a'] = 'fiction:drug-b'
    assert not cached_edge_supported(edge,{'text':text},entities)
    edge['quote'] = ''
    assert not cached_edge_supported(edge,{'text':text},entities)


@pytest.mark.parametrize('answer,expected',[
    ('Count: 2.5',None),('Count: 2,000',2000),('Count: -2',None),
    ('Count: 2. Correction: Count: 3.',None),('Count: 2,00',None),
    ('Count: 2.\n\nSources: 2024',2),('There are +2 entities',2),
])
def test_count_uses_complete_unambiguous_integer(answer,expected):
    assert count_value(answer)==expected
    if expected!=2:
        assert not score({'kind':'count','expected_count':2},{'answer':answer},Vocabulary([]))['passed']


@pytest.mark.parametrize('field',['subject','object','evidence'])
@pytest.mark.parametrize('blank',['','  \n'])
def test_extraction_schema_rejects_blank_support(field,blank):
    payload = {'subject':'Asterol','object':'Orion syndrome','relation':'CONTRAINDICATED_FOR',
               'evidence':'Asterol is contraindicated for Orion syndrome.','confidence':0.9}
    payload[field] = blank
    with pytest.raises(ValidationError):
        Relation.model_validate(payload)


def test_unrelated_quote_does_not_support_entity_cooccurrence():
    payload = {'subject':'Asterol','object':'Orion syndrome','relation':'CONTRAINDICATED_FOR',
               'evidence':'These are glossary entries.','confidence':0.9}
    model = Model(plan={'relations':[payload]})
    assert extract(model,'Asterol. Orion syndrome. These are glossary entries.')==[]
    payload['evidence'] = 'Asterol is contraindicated for Orion syndrome.'
    assert len(extract(model,payload['evidence']))==1


def test_multi_turn_accounting_includes_history_and_turn_traces():
    results = [{'answer':'Asterol','focus':['Asterol'],'intent':'indications','trace_id':str(i)*32,
                'contexts':[ENTITIES[0]],'failure_stage':None,'refused':False,
                'latency_s':latency,'usage':usage}
               for i,latency,usage in [(1,0.3,{'calls':2,'prompt_tokens':100,'completion_tokens':20}),
                                       (2,0.7,{'calls':1,'prompt_tokens':7,'completion_tokens':3})]]
    class Client:
        def ask(self,question,history):
            return results[len(history)]
    case = {'id':'fiction','category':'multi_turn','kind':'list','expected':['fiction:drug-a'],
            'history_questions':['What is Asterol?'],'question':'What about it?'}
    record = evaluate_case(Client(),case,Vocabulary(ENTITIES),SimpleNamespace(compare=lambda *args:None))
    assert record['usage']=={'calls':3,'prompt_tokens':107,'completion_tokens':23}
    assert record['latency_s']==1 and record['final_turn_latency_s']==0.7
    assert [t['result']['trace_id'] for t in record['turns']]==['1'*32,'2'*32]
    assert record['score']['passed']


def test_offline_rescore_changes_bad_count_without_mutating_history(tmp_path,monkeypatch):
    source = tmp_path/'archived_summary.json'
    detail = tmp_path/'archived_round1.jsonl'
    dataset,vocab,output = tmp_path/'cases.jsonl',tmp_path/'vocab.json',tmp_path/'rescored_summary.json'
    case = {'id':'fiction','category':'multi_turn','kind':'count','expected_count':2,
            'question':'Count the entities','history_questions':['What entities?']}
    result = {'answer':'Count: 2.5','contexts':[],'refused':False,'failure_stage':None}
    prior = {'rounds':1,'evaluated_ids':['fiction'],'total_available':1,'split':'test','system':'hybrid','phase':3}
    source.write_text(json.dumps(prior),encoding='utf8')
    detail.write_text(json.dumps({'id':'fiction','category':'multi_turn','score':{'passed':True},
        'execution_exact':None,'failure_stage':None,'latency_s':0.7,
        'usage':{'calls':1,'prompt_tokens':7,'completion_tokens':3},'result':result})+'\n',encoding='utf8')
    dataset.write_text(json.dumps(case)+'\n',encoding='utf8')
    vocab.write_text('[]',encoding='utf8')
    before = source.read_bytes(),detail.read_bytes()
    monkeypatch.setattr(sys,'argv',['eval.rescore','--source',str(source),'--dataset',str(dataset),
        '--vocabulary',str(vocab),'--output',str(output)])
    rescore.main()
    measured = json.loads(output.read_text(encoding='utf8'))
    assert measured['pass_rate_mean']==0 and not measured['accounting_complete']
    assert measured['new_model_calls']==0 and (source.read_bytes(),detail.read_bytes())==before
    with pytest.raises(SystemExit,match='new output path'):
        rescore.main()
