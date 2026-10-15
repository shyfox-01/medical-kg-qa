"""Idempotent fictional fixture import; refuses a populated non-fixture database."""

import argparse
import json

from medkg.config import ROOT
from medkg.graph.store import GraphStore


def load(store, allow_mixed=False):
    other = store.read('MATCH (n) WHERE n.uid IS NULL OR NOT n.uid STARTS WITH "synthetic:" '
                       'RETURN count(n) AS count')[0]['count']
    if other and not allow_mixed:
        raise RuntimeError('Synthetic-only import requires an empty or fictional-only database')
    fixtures = ROOT/'tests/fixtures'
    nodes = json.loads((fixtures/'entities.json').read_text(encoding='utf8'))
    edges = json.loads((fixtures/'edges.json').read_text(encoding='utf8'))
    store.create_schema()
    store.load(nodes,edges)
    vector = [1.0]+[0.0]*383
    store.write('MERGE (d:Document {uid:"synthetic:document"}) '
        'SET d.name="Fictional fixture",d.synonyms=[],d.source="synthetic",d.url="https://example.invalid/fixture" '
        'MERGE (c:Chunk {uid:"synthetic:chunk"}) SET c.name="Fictional summary",c.synonyms=[], '
        'c.section="summary",c.text="Fictional Virell syndrome is associated with fictional Glimmer sign.",c.embedding=$vector '
        'MERGE (d)-[:HAS_CHUNK]->(c) WITH d,c MATCH (n:Disease {uid:"synthetic:disease-a"}) '
        'MERGE (d)-[:ABOUT]->(n) MERGE (c)-[:MENTIONS]->(n)',{'vector':vector})


def cleanup(store):
    store.write('MATCH (n) WHERE n.uid STARTS WITH "synthetic:" DETACH DELETE n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--allow-mixed',action='store_true',help='Explicit local temporary-fixture opt-in')
    parser.add_argument('--cleanup',action='store_true',help='Delete fictional namespace only')
    args = parser.parse_args()
    store = GraphStore()
    try:
        cleanup(store) if args.cleanup else load(store,args.allow_mixed)
        print('Synthetic fixture cleanup complete' if args.cleanup else 'Synthetic fixture loaded')
    finally:
        store.close()


if __name__=='__main__':
    main()
