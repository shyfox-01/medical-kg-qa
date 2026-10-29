import json
import os
import subprocess
import sys
import uuid

import numpy as np
import pytest
from fastapi.testclient import TestClient

from eval.client import SystemClient
from medkg.api.app import create_app
from medkg.config import ROOT, Settings
from medkg.graph.guard import CypherRejected
from medkg.graph.store import GraphStore
from medkg.llm import FakeLLM
from medkg.qa.pipeline import Pipeline
from medkg.retrieval import expand, fulltext, templates, vector
from scripts.load_synthetic import load

pytestmark = pytest.mark.integration


@pytest.fixture(scope='module')
def fictional():
    if not os.getenv('MEDKG_INTEGRATION'):
        pytest.skip('Set MEDKG_INTEGRATION=1')
    store = GraphStore()
    try:
        # Integration fixtures must never be mixed into the research graph.
        load(store)
        store.read('CALL db.awaitIndexes(60)',timeout=70)
        yield store
    finally:
        store.close()


def test_parameterized_count_and_reverse(fictional):
    q,p = templates.query('indications',['synthetic:drug-a'],count=True)
    assert fictional.run_generated(q,p).rows[0]['count']==1
    q,p = templates.query('drugs_for',['synthetic:disease-a'])
    assert {r['uid'] for r in fictional.run_generated(q,p).rows}=={'synthetic:drug-a'}


def test_undirected_and_two_hop(fictional):
    q,p = templates.query('interactions',['synthetic:drug-b'])
    assert fictional.run_generated(q,p).rows[0]['uid']=='synthetic:drug-a'
    result = fictional.run_generated('MATCH (d:Drug {uid:$uid})-[:INDICATED_FOR]->(:Disease)'
        '-[:HAS_PHENOTYPE]->(p:Phenotype) RETURN p.uid AS uid',{'uid':'synthetic:drug-a'})
    assert result.rows==[{'uid':'synthetic:phenotype-a'}]
    assert expand.search(fictional,['synthetic:disease-a'],hops=2).rows


def test_trusted_text_indexes(fictional):
    assert any(r['uid']=='synthetic:drug-a' for r in fulltext.search(fictional,'Asterol',label='Drug').rows)
    document = next(r for r in fulltext.search(fictional,'Fictional fixture',label='Document').rows
                    if r['uid']=='synthetic:document')
    assert document['source']=='synthetic' and document['url']=='https://example.invalid/fixture'
    result = fictional.read('CALL db.index.vector.queryNodes("chunk_embedding",8,$v) '
        'YIELD node,score RETURN node.uid AS uid,score',{'v':[1.0]+[0.0]*383})
    assert result[0]['uid']=='synthetic:chunk'


def test_hybrid_chunk_retrieval_runs_on_both_indexes(fictional,monkeypatch):
    monkeypatch.setattr(vector.EMBEDDER,'encode',lambda texts: np.array([[1.0]+[0.0]*383],dtype=np.float32))
    assert vector.sparse(fictional,'Glimmer sign')[0]['uid']=='synthetic:chunk'
    assert vector.dense(fictional,'anything')[0]['uid']=='synthetic:chunk'
    rows = vector.search(fictional,'Glimmer sign',uids=['synthetic:disease-a']).rows
    assert rows[0]['uid']=='synthetic:chunk' and rows[0]['url']=='https://example.invalid/fixture'


def test_conflicting_claims_preserve_both_sources_and_evidence(fictional):
    fictional.write('MATCH (a:Drug {uid:"synthetic:drug-a"})-[r:INDICATED_FOR]->'
        '(b:Disease {uid:"synthetic:disease-a"}) SET r.conflict=true '
        'MERGE (a)-[s:CONTRAINDICATED_FOR]->(b) SET s.conflict=true,'
        's.source="synthetic-extracted",s.evidence=["synthetic:chunk"]')
    try:
        entities = [r for r in fictional.entities() if r['uid'].startswith('synthetic:')]
        pipeline = Pipeline(store=fictional,llm=FakeLLM(),entities=entities)
        result = pipeline.ask('What is Asterol indicated for?')
        assert result['failure_stage'] is None
        assert 'INDICATED_FOR Virell syndrome [synthetic]' in result['answer']
        assert 'CONTRAINDICATED_FOR Virell syndrome [synthetic-extracted]' in result['answer']
        assert 'https://example.invalid/fixture' in result['answer']
        assert any(r.get('uid')=='synthetic:chunk' for r in result['contexts'])
    finally:
        fictional.write('MATCH (a:Drug {uid:"synthetic:drug-a"})-[r:INDICATED_FOR]->'
            '(:Disease {uid:"synthetic:disease-a"}) SET r.conflict=false')
        fictional.write('MATCH (:Drug {uid:"synthetic:drug-a"})-[r:CONTRAINDICATED_FOR]->'
            '(:Disease {uid:"synthetic:disease-a"}) DELETE r')


@pytest.mark.parametrize('question,anchor,relation,other,expected',[
    ('Which drugs target genes associated with Virell syndrome?',
     'synthetic:disease-a','ASSOCIATED_WITH','TARGETS','Asterol'),
    ('Which diseases are associated with genes targeted by Asterol?',
     'synthetic:drug-a','TARGETS','ASSOCIATED_WITH','Virell syndrome'),
])
def test_multi_hop_questions_reach_planner_and_traverse_both_relations(
        fictional,question,anchor,relation,other,expected):
    class PlannedModel(FakeLLM):
        def chat_json(self,messages,max_tokens=1400):
            self.usage['calls'] += 1
            if '"cypher"' not in messages[0]['content']:
                return {'steps':[{'tool':'text2cypher','args':{'question':question}}]}
            start,end = ('Disease','Drug') if relation=='ASSOCIATED_WITH' else ('Drug','Disease')
            return {'cypher':f'MATCH (a:{start} {{uid:$uid}})-[r1:{relation}]->(:Gene)'
                f'<-[r2:{other}]-(b:{end}) RETURN DISTINCT b.uid AS uid,b.name AS name,'
                '[r1.source,r2.source] AS sources LIMIT 25','params':{'uid':anchor}}
    entities = [r for r in fictional.entities() if r['uid'].startswith('synthetic:')]
    result = Pipeline(settings=Settings(reasoning='plan'),store=fictional,llm=PlannedModel(),entities=entities).ask(question)
    assert result['failure_stage'] is None and result['route']=='planner'
    assert expected in result['answer'] and result['refused'] is False
    assert relation in result['cypher'][0] and other in result['cypher'][0]


def test_template_collection_union_and_count_are_order_independent(fictional):
    anchors = ['synthetic:disease-a','synthetic:disease-b']
    for uids in (anchors,anchors[::-1]):
        q,p = templates.query('genes',uids)
        rows = fictional.run_generated(q,p).rows
        assert {r['uid'] for r in rows}=={'synthetic:gene-a'}
        assert rows[0]['anchor_uid']=='synthetic:disease-a'
        q,p = templates.query('genes',uids,count=True)
        assert fictional.run_generated(q,p).rows[0]['count']==1


def test_global_generated_row_bound_and_union_rejection(fictional):
    statement = 'WITH 1 AS seed UNWIND range(1,400) AS n RETURN n AS uid LIMIT 999'
    result = fictional.run_generated(statement)
    assert len(result.rows)==200 and result.truncated
    before = len(fictional.executed_statements)
    with pytest.raises(CypherRejected,match='UNION'):
        fictional.run_generated(statement+' UNION ALL '+statement)
    assert len(fictional.executed_statements)==before


def test_non_gene_multi_hop_traversal(fictional):
    class PlannedModel(FakeLLM):
        def chat_json(self,messages,max_tokens=1400):
            self.usage['calls'] += 1
            if '"cypher"' not in messages[0]['content']:
                return {'steps':[{'tool':'text2cypher','args':{'question':'Fictional symptoms'}}]}
            return {'cypher':'MATCH (a:Drug {uid:$uid})-[r1:INDICATED_FOR]->(:Disease)'
                '-[r2:HAS_PHENOTYPE]->(p:Phenotype) RETURN DISTINCT p.uid AS uid,p.name AS name,'
                '[r1.source,r2.source] AS sources LIMIT 25','params':{'uid':'synthetic:drug-a'}}
    entities = [e for e in fictional.entities() if e['uid'].startswith('synthetic:')]
    result = Pipeline(settings=Settings(reasoning='plan'),store=fictional,llm=PlannedModel(),entities=entities).ask(
        'What symptoms are associated with diseases treated by Asterol?')
    assert result['route']=='planner' and result['failure_stage'] is None
    assert 'Glimmer sign' in result['answer'] and result['response_status']=='answered'
    assert 'INDICATED_FOR' in result['cypher'][0] and 'HAS_PHENOTYPE' in result['cypher'][0]


def test_reverse_non_gene_multi_hop_traversal(fictional):
    class PlannedModel(FakeLLM):
        def chat_json(self,messages,max_tokens=1400):
            self.usage['calls'] += 1
            if '"cypher"' not in messages[0]['content']:
                return {'steps':[{'tool':'text2cypher','args':{'question':'Fictional effects'}}]}
            return {'cypher':'MATCH (a:Disease {uid:$uid})<-[r1:INDICATED_FOR]-(d:Drug)'
                '-[r2:HAS_SIDE_EFFECT]->(p:Phenotype) RETURN DISTINCT p.uid AS uid,p.name AS name,'
                '[r1.source,r2.source] AS sources LIMIT 25','params':{'uid':'synthetic:disease-a'}}
    fictional.write('MATCH (d:Drug {uid:"synthetic:drug-a"}),(p:Phenotype '
        '{uid:"synthetic:phenotype-a"}) MERGE (d)-[r:HAS_SIDE_EFFECT]->(p) SET r.source="synthetic"')
    try:
        entities = [e for e in fictional.entities() if e['uid'].startswith('synthetic:')]
        result = Pipeline(settings=Settings(reasoning='plan'),store=fictional,llm=PlannedModel(),entities=entities).ask(
            'What side effects are associated with drugs treating Virell syndrome?')
        assert result['route']=='planner' and result['failure_stage'] is None
        assert 'Glimmer sign' in result['answer'] and result['response_status']=='answered'
        assert 'INDICATED_FOR' in result['cypher'][0] and 'HAS_SIDE_EFFECT' in result['cypher'][0]
    finally:
        fictional.write('MATCH (:Drug {uid:"synthetic:drug-a"})-[r:HAS_SIDE_EFFECT]->'
            '(:Phenotype {uid:"synthetic:phenotype-a"}) WHERE r.source="synthetic" DELETE r')


def test_invalid_plan_recovers_through_guarded_path_and_records_actual_constraint(fictional):
    class RecoveringModel(FakeLLM):
        def chat_json(self,messages,max_tokens=1400):
            self.usage['calls'] += 1
            if '"cypher"' not in messages[0]['content']:
                return {'steps':[{'tool':'text2cypher','args':{'relation':'unsupported argument'}}]}
            return {'cypher':'MATCH (a:Disease {uid:$uid})-[r1:ASSOCIATED_WITH]->(:Gene)'
                '<-[r2:TARGETS]-(d:Drug) RETURN DISTINCT d.uid AS uid,d.name AS name,'
                '[r1.source,r2.source] AS sources LIMIT 25','params':{'uid':'synthetic:disease-a'}}
    entities = [e for e in fictional.entities() if e['uid'].startswith('synthetic:')]
    result = Pipeline(settings=Settings(reasoning='plan'),store=fictional,llm=RecoveringModel(),entities=entities).ask(
        'Which drugs target genes associated with Virell syndrome?')
    assert result['failure_stage'] is None and result['planning_fallback']=='invalid_plan_schema'
    assert 'Asterol' in result['answer']
    context = next(c for c in result['contexts'] if c.get('role')=='executed_graph_queries')
    assert context['queries']==result['queries'] and 'ASSOCIATED_WITH' in context['queries'][0]['cypher']


def test_shared_target_query_excludes_a_single_anchor_only_neighbor(fictional):
    fictional.write('MATCH (d:Disease {uid:"synthetic:disease-b"}),(g:Gene '
        '{uid:"synthetic:gene-a"}) MERGE (d)-[r:ASSOCIATED_WITH]->(g) SET r.source="synthetic"')
    try:
        result = fictional.run_generated('MATCH (a:Disease {uid:$a})-[r1:ASSOCIATED_WITH]->(g:Gene)'
            '<-[r2:ASSOCIATED_WITH]-(b:Disease {uid:$b}) RETURN DISTINCT g.uid AS uid,'
            'g.name AS name,[r1.source,r2.source] AS sources LIMIT 25',
            {'a':'synthetic:disease-a','b':'synthetic:disease-b'})
        assert {r['uid'] for r in result.rows}=={'synthetic:gene-a'}
        # Phenotypes present on just one anchor must not enter an intersection.
        empty = fictional.run_generated('MATCH (a:Disease {uid:$a})-[:HAS_PHENOTYPE]->(p:Phenotype)'
            '<-[:HAS_PHENOTYPE]-(b:Disease {uid:$b}) RETURN DISTINCT p.uid AS uid LIMIT 25',
            {'a':'synthetic:disease-a','b':'synthetic:disease-b'})
        assert empty.rows==[]
    finally:
        fictional.write('MATCH (:Disease {uid:"synthetic:disease-b"})-[r:ASSOCIATED_WITH]->'
            '(:Gene {uid:"synthetic:gene-a"}) WHERE r.source="synthetic" DELETE r')


def test_scoped_assertion_reconciliation_and_conflict_flags(fictional):
    a,b = 'synthetic:drug-a','synthetic:disease-a'
    edge = {'a':a,'b':b,'type':'CONTRAINDICATED_FOR','source':'openfda_extracted',
            'evidence':['synthetic:selected'],'confidence':0.9,'extractor_version':'fictional'}
    def read():
        return fictional.read('MATCH (:Drug {uid:$a})-[r:CONTRAINDICATED_FOR]->'
            '(:Disease {uid:$b}) WHERE r.source="openfda_extracted" '
            'RETURN r.evidence AS evidence,r.conflict AS conflict',{'a':a,'b':b})
    def flag():
        return fictional.read('MATCH (:Drug {uid:$a})-[r:INDICATED_FOR]->(:Disease {uid:$b}) '
            'RETURN r.conflict AS conflict',{'a':a,'b':b})[0]['conflict']
    try:
        # Use an isolated source value for this temporary PrimeKG-compatible edge.
        fictional.write('MATCH (:Drug {uid:$a})-[r:INDICATED_FOR]->(:Disease {uid:$b}) '
            'SET r.source="primekg"',{'a':a,'b':b})
        fictional.reconcile_extracted({'synthetic:outside'},[{**edge,'evidence':['synthetic:outside']}])
        fictional.reconcile_extracted({'synthetic:selected'},[edge])
        assert read()[0]['evidence']==['synthetic:outside','synthetic:selected']
        assert read()[0]['conflict'] and flag()
        fictional.reconcile_extracted({'synthetic:selected'},[])
        assert read()[0]['evidence']==['synthetic:outside'] and flag()
        fictional.reconcile_extracted({'synthetic:selected'},[])
        assert read()[0]['evidence']==['synthetic:outside']
        fictional.reconcile_extracted({'synthetic:outside'},[])
        assert read()==[] and not flag()
    finally:
        fictional.write('MATCH (:Drug {uid:$a})-[r:CONTRAINDICATED_FOR]->(:Disease {uid:$b}) '
            'WHERE r.source="openfda_extracted" DELETE r',{'a':a,'b':b})
        fictional.write('MATCH (:Drug {uid:$a})-[r:INDICATED_FOR]->(:Disease {uid:$b}) '
            'SET r.source="synthetic",r.conflict=false',{'a':a,'b':b})


def test_public_cli_returns_a_verified_database_answer(fictional):
    result = subprocess.run([
        sys.executable, '-m', 'medkg.cli', 'What is Asterol indicated for?',
        '--phase', '3', '--fake', '--json',
    ], cwd=ROOT, capture_output=True, text=True, encoding='utf8', timeout=45)
    assert result.returncode == 0, result.stderr
    answer = json.loads(result.stdout)
    assert answer['failure_stage'] is None and answer['response_status'] == 'answered'
    assert 'Virell syndrome' in answer['answer']
    assert answer['queries'] and any(row.get('uid') == 'synthetic:disease-a'
                                     for row in answer['contexts'])


def test_fixture_loader_refuses_unidentified_existing_nodes(fictional):
    identity = uuid.uuid4().hex
    fictional.write('CREATE (:IntegrationGuardProbe {probe_id:$id})', {'id': identity})
    try:
        with pytest.raises(RuntimeError, match='empty or fictional-only'):
            load(fictional)
        assert fictional.read('MATCH (n:IntegrationGuardProbe {probe_id:$id}) '
                              'RETURN count(n) AS count', {'id': identity}) == [{'count': 1}]
    finally:
        fictional.write('MATCH (n:IntegrationGuardProbe {probe_id:$id}) DELETE n', {'id': identity})


def test_public_stdio_preserves_conversation_focus_with_database(fictional):
    client = SystemClient(phase=3, fake=True)
    try:
        first = client.ask('Which genes are associated with Virell syndrome?', [])
        assert first['failure_stage'] is None and 'FICTGENE1' in first['answer']
        history = [{'question': 'Which genes are associated with Virell syndrome?',
                    'focus': first['focus'], 'intent': first['intent']}]
        followup = client.ask('What are its symptoms?', history)
        assert followup['failure_stage'] is None and 'Glimmer sign' in followup['answer']
        assert followup['trace_id'] != first['trace_id']
    finally:
        client.close()


def test_http_and_sse_use_database_evidence_and_consistent_final_answer(fictional):
    settings = Settings(phase=3, cache=False, llm_api_key='synthetic',
                        llm_model='synthetic', llm_base_url='https://example.invalid')
    # A separate driver lets the API own its lifecycle without closing the fixture.
    pipeline = Pipeline(settings=settings, store=GraphStore(settings), llm=FakeLLM(),
                        entities=[row for row in fictional.entities()
                                  if row['uid'].startswith('synthetic:')])
    question = 'How many genes are associated with Virell syndrome?'
    with TestClient(create_app(pipeline)) as client:
        assert client.get('/health').status_code == 200
        assert client.get('/ready').json()['status'] == 'ready'
        response = client.post('/ask', json={'question': question})
        assert response.status_code == 200
        answer = response.json()
        assert answer['failure_stage'] is None and 'Count: 1' in answer['answer']
        assert answer['queries'] and any(row.get('count') == 1 for row in answer['contexts'])
        streamed = client.post('/ask/stream', json={'question': question})
        assert streamed.status_code == 200
        assert streamed.headers['content-type'].startswith('text/event-stream')
        events = []
        for block in streamed.text.strip().split('\n\n'):
            name, data = block.split('\n', 1)
            events.append((name.removeprefix('event: '), json.loads(data.removeprefix('data: '))))
        assert events[0][0] == 'status' and events[-1][0] == 'result'
        final = events[-1][1]
        assert final['failure_stage'] is None and final['answer'] == answer['answer']
        chunks = [payload for name, payload in events if name == 'answer']
        assert ''.join(chunk['text'] for chunk in chunks) == final['answer']
        assert all(chunk['trace_id'] == final['trace_id'] for chunk in chunks)
