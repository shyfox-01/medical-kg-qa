import os

import pytest

from medkg.graph.store import GraphStore
from medkg.llm import FakeLLM
from medkg.qa.pipeline import Pipeline
from medkg.retrieval import expand, fulltext, templates
from scripts.load_synthetic import cleanup, load

pytestmark = pytest.mark.integration


@pytest.fixture(scope='module')
def fictional():
    if not os.getenv('MEDKG_INTEGRATION'):
        pytest.skip('Set MEDKG_INTEGRATION=1')
    store = GraphStore()
    synthetic_only = bool(os.getenv('MEDKG_SYNTHETIC_ONLY'))
    load(store,allow_mixed=not synthetic_only)
    store.read('CALL db.awaitIndexes(60)',timeout=70)
    yield store
    if not synthetic_only:
        cleanup(store)
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
