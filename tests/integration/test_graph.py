import os

import pytest
from neo4j.exceptions import Neo4jError

from medkg.config import ROOT
from medkg.graph.store import GraphStore
from medkg.ingest.ontology import load_obo
from medkg.ingest.primekg import read_graph

pytestmark = pytest.mark.integration


@pytest.fixture
def store():
    if not os.getenv('MEDKG_INTEGRATION'):
        pytest.skip('Set MEDKG_INTEGRATION=1 to run database tests')
    graph = GraphStore()
    graph.verify()
    yield graph
    graph.close()


def test_read_access_enforced(store):
    with pytest.raises(Neo4jError):
        store.read('CREATE (n:Disease {uid:"test:forbidden"}) RETURN n')


def test_csv_counts_match_database(store):
    if not os.getenv('MEDKG_REAL_COUNTS'):
        pytest.skip('Set MEDKG_REAL_COUNTS=1 for full CSV count comparison')
    raw = ROOT/'data/raw'
    _,_,report = read_graph(raw/'kg.csv',load_obo(raw/'mondo.obo'),load_obo(raw/'hp.obo'))
    actual = store.counts()
    assert {k:actual['nodes'][k] for k in report['nodes']}==report['nodes']
    relations = {row['type']:row['count'] for row in store.read(
        'MATCH ()-[r]->() WHERE r.source="primekg" RETURN type(r) AS type,count(*) AS count',timeout=60)}
    assert relations==report['relations']
