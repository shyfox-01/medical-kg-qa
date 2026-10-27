import argparse
import json
import time
from collections import Counter

from medkg.config import ROOT
from medkg.embeddings import Embeddings
from medkg.graph.store import GraphStore, entity_alias_properties
from medkg.ingest import medlineplus, openfda
from medkg.ingest.link import mentions
from medkg.ingest.ontology import load_obo
from medkg.qa.linker import Linker


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--openfda-limit',type=int,default=500)
    parser.add_argument('--links-only',action='store_true',
                        help='Only refresh document links; text, embeddings and mentions stay as loaded')
    args = parser.parse_args()
    if not 1<=args.openfda_limit<=500:
        parser.error('openFDA limit must be 1–500')
    raw,processed = ROOT/'data/raw',ROOT/'data/processed'
    entities = json.loads((processed/'entities.json').read_text(encoding='utf8'))
    store = GraphStore()
    try:
        store.create_schema()
        ranked = store.read('MATCH (d:Drug)-[:INDICATED_FOR]->(:Disease) '
                            'RETURN d.uid AS uid,d.name AS name,count(*) AS count '
                            'ORDER BY count DESC,uid LIMIT 500')
        records = openfda.fetch(ranked[:args.openfda_limit],raw)
        timestamp = time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
        documents,chunks = medlineplus.parse(raw/'medlineplus.xml',entities,load_obo(raw/'mondo.obo'),timestamp)
        fda_documents,fda_chunks,fda_report = openfda.parse(records,entities,timestamp)
        documents += fda_documents
        chunks += fda_chunks
        if args.links_only:
            urls = {d['uid']:d['url'] for d in documents}
            store.write('UNWIND $rows AS row MATCH (d:Document {uid:row.uid}) SET d.url=row.url',
                        {'rows':[{'uid':uid,'url':url} for uid,url in urls.items()]})
            changed = 0
            for name,key in (('documents.jsonl','uid'),('chunks.jsonl','document_uid')):
                path = processed/name
                rows = [json.loads(line) for line in path.read_text(encoding='utf8').splitlines()]
                for row in rows:
                    if row[key] in urls and row.get('url')!=urls[row[key]]:
                        row['url'] = urls[row[key]]
                        changed += name=='documents.jsonl'
                path.write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf8')
            print(f'Refreshed links of {changed} documents',flush=True)
            return
        for label in ('Disease','Drug','Phenotype','Gene'):
            rows = [{'uid':e['uid'],**entity_alias_properties(e)} for e in entities if e['label']==label]
            store.write(f'UNWIND $rows AS row MATCH (n:{label} {{uid:row.uid}}) '
                        'SET n.synonyms=row.synonyms,n.exact_synonyms=row.exact_synonyms',{'rows':rows})
        for i in range(0,len(documents),1000):
            rows = [{k:v for k,v in d.items() if k!='about'} for d in documents[i:i+1000]]
            store.write('UNWIND $rows AS row MERGE (d:Document {uid:row.uid}) SET d += row',{'rows':rows})
        about = [{'doc':d['uid'],'uid':uid} for d in documents for uid in d['about']]
        for label in ('Disease','Drug'):
            store.write('UNWIND $rows AS row MATCH (d:Document {uid:row.doc}),'
                        f'(n:{label} {{uid:row.uid}}) MERGE (d)-[:ABOUT]->(n)',{'rows':about})
        embedder = Embeddings()
        cached = processed/'chunk_embeddings.jsonl'
        old = {r['uid']:r for r in (json.loads(line) for line in cached.read_text(encoding='utf8').splitlines())} if cached.exists() else {}
        for i in range(0,len(chunks),64):
            batch = chunks[i:i+64]
            missing = [c for c in batch if c['uid'] not in old or old[c['uid']]['text']!=c['text']]
            if missing:
                vectors = embedder.encode([c['text'] for c in missing])
                with cached.open('a',encoding='utf8') as stream:
                    for chunk,vector in zip(missing,vectors,strict=True):
                        old[chunk['uid']] = {'uid':chunk['uid'],'text':chunk['text'],'embedding':vector.tolist()}
                        stream.write(json.dumps(old[chunk['uid']])+'\n')
            rows = [{k:v for k,v in c.items() if k not in ('about','document_uid','source','url')}
                    | {'embedding':old[c['uid']]['embedding'],'doc':c['document_uid']} for c in batch]
            store.write('UNWIND $rows AS row MATCH (d:Document {uid:row.doc}) '
                        'MERGE (c:Chunk {uid:row.uid}) SET c += row MERGE (d)-[:HAS_CHUNK]->(c)',{'rows':rows})
            print(f'Loaded chunks {min(i+64,len(chunks))}/{len(chunks)}',flush=True)
        linked = mentions(chunks,Linker(entities),processed/'unlinked_mentions.jsonl')
        # Recompute lexical edges after aliases change; never retain stale earlier matches.
        store.write('MATCH (d:Document)-[:HAS_CHUNK]->(c:Chunk)-[r:MENTIONS]->() '
                    'WHERE d.source IN ["medlineplus","openfda"] DELETE r')
        for label in ('Disease','Drug','Phenotype'):
            for i in range(0,len(linked),10000):
                store.write('UNWIND $rows AS row MATCH (c:Chunk {uid:row.a}),'
                            f'(n:{label} {{uid:row.b}}) MERGE (c)-[:MENTIONS]->(n)',{'rows':linked[i:i+10000]})
        (processed/'entities.json').write_text(json.dumps(entities),encoding='utf8')
        (processed/'documents.jsonl').write_text(''.join(json.dumps(d)+'\n' for d in documents),encoding='utf8')
        (processed/'chunks.jsonl').write_text(''.join(json.dumps(c)+'\n' for c in chunks),encoding='utf8')
        report = {'documents':dict(Counter(d['source'] for d in documents)),
                  'chunks':dict(Counter(c['source'] for c in chunks)),
                  'about_documents':sum(bool(d['about']) for d in documents),'openfda':fda_report,
                  'openfda_requests':len((raw/'openfda/requests.jsonl').read_text(encoding='utf8').splitlines()),
                  'mentions':len(linked),'graph_counts':store.counts()}
        (processed/'text_counts.json').write_text(json.dumps(report,indent=2),encoding='utf8')
        print(json.dumps(report,indent=2))
    finally:
        store.close()


if __name__=='__main__':
    main()
