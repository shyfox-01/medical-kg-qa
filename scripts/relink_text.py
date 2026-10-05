"""Refresh only lexical MENTIONS edges after cached text/alias ingestion."""

import json

from medkg.config import ROOT
from medkg.graph.store import GraphStore
from medkg.ingest.link import mentions
from medkg.qa.linker import Linker


def main():
    processed = ROOT/'data/processed'
    chunks = [json.loads(line) for line in (processed/'chunks.jsonl').read_text(encoding='utf8').splitlines()]
    entities = json.loads((processed/'entities.json').read_text(encoding='utf8'))
    linked = mentions(chunks,Linker(entities),processed/'unlinked_mentions.jsonl')
    store = GraphStore()
    try:
        store.write('MATCH (d:Document)-[:HAS_CHUNK]->(c:Chunk)-[r:MENTIONS]->() '
                    'WHERE d.source IN ["medlineplus","openfda"] DELETE r')
        for label in ('Disease','Drug','Phenotype'):
            for start in range(0,len(linked),10000):
                store.write('UNWIND $rows AS row MATCH (c:Chunk {uid:row.a}),'
                    f'(n:{label} {{uid:row.b}}) MERGE (c)-[:MENTIONS]->(n)',{'rows':linked[start:start+10000]})
        path = processed/'text_counts.json'
        report = json.loads(path.read_text(encoding='utf8'))
        report.update(mentions=len(linked),graph_counts=store.counts())
        path.write_text(json.dumps(report,indent=2),encoding='utf8')
        print(json.dumps({'mentions':len(linked),'actual_mentions':report['graph_counts']['relations']['MENTIONS']}))
    finally:
        store.close()


if __name__=='__main__':
    main()
