"""Repair FDA identities and cached assertions without downloads or LLM calls.

Copies affected files and graph records before applying reversible derived-data
updates. Existing text, chunk vectors and historical evaluations stay unchanged.
"""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np

from medkg.config import ROOT
from medkg.graph.store import GraphStore, entity_alias_properties
from medkg.ingest.extract import VERSION, cached_edge_supported
from medkg.ingest.link import mentions
from medkg.ingest.openfda import parse
from medkg.qa.linker import Linker
from scripts.check_artifacts import verify
from scripts.embed_entities import main as embed_aliases


def read_lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding='utf8').splitlines()]


def write_lines(path: Path,rows: list[dict]) -> None:
    temporary = path.with_suffix(path.suffix+'.repairing')
    temporary.write_text(''.join(json.dumps(row)+'\n' for row in rows),encoding='utf8')
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply',action='store_true',help='Apply the cached repair after backups')
    args = parser.parse_args()
    summary_path = ROOT/'eval/runs/cached_repair_summary.json'
    if args.apply and summary_path.exists():
        prior = json.loads(summary_path.read_text(encoding='utf8'))
        if prior.get('applied') and prior.get('repair_version')=='cached-text-1.0':
            checked = verify(ROOT)
            if not checked['passed']:
                raise RuntimeError('Previously repaired artifacts failed read-only verification')
            print(json.dumps({'already_applied':True,'summary':str(summary_path),
                              'artifact_verification':checked}))
            return
    processed = ROOT/'data/processed'
    work = ROOT/'.cache/fix-2026-10-05/artifact-repair'
    work.mkdir(parents=True,exist_ok=True)
    entities = json.loads((processed/'entities.json').read_text(encoding='utf8'))
    old_drugs = {e['uid']:list(e['synonyms']) for e in entities if e['label']=='Drug'}
    # Canonical CSV ingestion supplies no Drug synonyms. All additions in this
    # checkout originate in FDA labels, so rebuild from that clean baseline.
    for entity in entities:
        if entity['label']=='Drug':
            entity['synonyms'] = []
    records = [json.loads(path.read_text(encoding='utf8'))
               for path in sorted((ROOT/'data/raw/openfda').glob('*.json'))]
    fda_documents,_,stats = parse(records,entities,'cached-source-repair')
    new_about = {d['uid']:d['about'] for d in fda_documents}
    documents = read_lines(processed/'documents.jsonl')
    affected_docs = [d for d in documents if d['source']=='openfda']
    for document in affected_docs:
        document['about'] = new_about.get(document['uid'],[])
    by_doc = {d['uid']:d for d in documents}
    chunks = read_lines(processed/'chunks.jsonl')
    for chunk in chunks:
        if chunk['source']=='openfda':
            chunk['about'] = by_doc[chunk['document_uid']]['about']
    by_chunk = {c['uid']:c for c in chunks}
    by_entity = {e['uid']:e for e in entities}
    edges = read_lines(processed/'extracted_edges.jsonl')
    supported,quarantined = [],[]
    for edge in edges:
        target = supported if any(cached_edge_supported(edge,by_chunk[uid],by_entity)
            for uid in edge.get('evidence',[]) if uid in by_chunk) else quarantined
        target.append(edge)
    aliases = {alias for e in entities for alias in [e['name'],*e['synonyms']]}
    cached_aliases = json.loads((processed/'vector_aliases.json').read_text(encoding='utf8'))
    missing_texts = aliases-{a['text'] for a in cached_aliases}
    if missing_texts:
        raise RuntimeError('Repair needs uncached alias vectors; no automatic download is permitted')
    progress = json.loads((processed/'vector_progress.json').read_text(encoding='utf8'))
    vectors = np.load(processed/'vector_corpus.npy',mmap_mode='r')
    if progress['completed']!=progress['total'] or vectors.shape!=(progress['total'],384):
        raise RuntimeError('Vector checkpoint is incomplete; do not rewrite its provenance')
    vectors._mmap.close()
    changes = sum(old_drugs[e['uid']]!=e['synonyms'] for e in entities if e['label']=='Drug')
    report = {'repair_version':'cached-text-1.0','applied':False,'downloads':0,'llm_calls':0,
        'changed_drug_alias_sets':changes,'fda_documents':len(affected_docs),'fda_parse':stats,
        'unlinked_fda_documents':sum(not d['about'] for d in affected_docs),
        'retained_assertions':len(supported),'quarantined_assertions':len(quarantined),
        'chunk_texts_changed':0,'chunk_embeddings_recomputed':0}
    if not args.apply:
        print(json.dumps(report,indent=2))
        return
    backup = work/'before'
    backup.mkdir(exist_ok=True)
    files = ['entities.json','documents.jsonl','chunks.jsonl','alias_vectors.npy',
        'vector_aliases.json','vector_corpus.jsonl','vector_progress.json','text_counts.json',
        'extracted_edges.jsonl','extractions.jsonl']
    checksums = {}
    for name in files:
        source,saved = processed/name,backup/name
        if not saved.exists():
            shutil.copyfile(source,saved)
            with source.open('rb') as original,saved.open('rb') as copied:
                valid = hashlib.file_digest(original,'sha256').hexdigest()==hashlib.file_digest(copied,'sha256').hexdigest()
            if not valid:
                raise RuntimeError('Backup verification failed')
        with saved.open('rb') as stream:
            checksums[name] = hashlib.file_digest(stream,'sha256').hexdigest()
    (backup/'manifest.json').write_text(json.dumps(checksums,indent=2),encoding='utf8')
    store = GraphStore()
    try:
        store.verify()
        snapshot = backup/'graph.json'
        if not snapshot.exists():
            graph = {'drugs':store.read('MATCH (n:Drug) RETURN n.uid AS uid,n.synonyms AS synonyms, '
                                       'n.exact_synonyms AS exact_synonyms'),
                'about':store.read('MATCH (d:Document)-[:ABOUT]->(n) WHERE d.source="openfda" '
                    'RETURN d.uid AS a,n.uid AS b'),
                'mentions':store.read('MATCH (d:Document)-[:HAS_CHUNK]->(c:Chunk)-[:MENTIONS]->(n) '
                    'WHERE d.source IN ["openfda","medlineplus"] RETURN c.uid AS a,n.uid AS b'),
                'extracted':store.read('MATCH (a)-[r]->(b) WHERE r.source="openfda_extracted" '
                    'RETURN a.uid AS a,b.uid AS b,type(r) AS type,properties(r) AS props'),
                'primekg_conflicts':store.read('MATCH (a)-[r]->(b) WHERE r.source="primekg" AND r.conflict=true '
                    'RETURN a.uid AS a,b.uid AS b,type(r) AS type')}
            snapshot.write_text(json.dumps(graph),encoding='utf8')
        (processed/'entities.json').write_text(json.dumps(entities),encoding='utf8')
        write_lines(processed/'documents.jsonl',documents)
        write_lines(processed/'chunks.jsonl',chunks)
        embed_aliases()
        corpus = processed/'vector_corpus.jsonl'
        temporary = corpus.with_suffix('.repairing')
        total = 0
        with corpus.open(encoding='utf8') as source,temporary.open('w',encoding='utf8') as destination:
            for line in source:
                row = json.loads(line)
                if row['uid'] in by_chunk:
                    if row['text']!=by_chunk[row['uid']]['text']:
                        raise RuntimeError('Cached corpus text changed; vectors cannot be reused')
                    row['about'] = by_chunk[row['uid']]['about']
                destination.write(json.dumps(row)+'\n')
                total += 1
        if total!=progress['total']:
            raise RuntimeError('Corpus row count changed during metadata-only repair')
        temporary.replace(corpus)
        with corpus.open('rb') as stream:
            progress['sha256'] = hashlib.file_digest(stream,'sha256').hexdigest()
        (processed/'vector_progress.json').write_text(json.dumps(progress),encoding='utf8')
        linked = mentions(chunks,Linker(entities),processed/'unlinked_mentions.jsonl')
        drugs = [{'uid':e['uid'],**entity_alias_properties(e)} for e in entities if e['label']=='Drug']
        store.write('UNWIND $rows AS row MATCH (n:Drug {uid:row.uid}) '
                    'SET n.synonyms=row.synonyms,n.exact_synonyms=row.exact_synonyms',{'rows':drugs})
        store.write('MATCH (d:Document)-[r:ABOUT]->() WHERE d.uid IN $uids DELETE r',
                    {'uids':[d['uid'] for d in affected_docs]})
        store.write('UNWIND $rows AS row MATCH (d:Document {uid:row.a}),(n:Drug {uid:row.b}) '
                    'MERGE (d)-[:ABOUT]->(n)',{'rows':[{'a':d['uid'],'b':uid} for d in affected_docs for uid in d['about']]})
        store.write('MATCH (d:Document)-[:HAS_CHUNK]->(c:Chunk)-[r:MENTIONS]->() '
                    'WHERE d.source IN ["openfda","medlineplus"] DELETE r')
        for label in ('Disease','Drug','Phenotype'):
            for start in range(0,len(linked),10000):
                store.write('UNWIND $rows AS row MATCH (c:Chunk {uid:row.a}),'
                    f'(n:{label} {{uid:row.b}}) MERGE (c)-[:MENTIONS]->(n)',{'rows':linked[start:start+10000]})
        store.write('UNWIND $rows AS row MATCH (a:Drug {uid:row.a})-[r:INDICATED_FOR]->'
                    '(b:Disease {uid:row.b}) WHERE r.source="primekg" SET r.conflict=false',
                    {'rows':[e for e in edges if e['type']=='CONTRAINDICATED_FOR']})
        store.write('MATCH ()-[r]->() WHERE r.source="openfda_extracted" DELETE r')
        for edge in supported:
            edge['conflict'] = False
            if edge['type']=='CONTRAINDICATED_FOR':
                found = store.read('MATCH (a:Drug {uid:$a})-[r:INDICATED_FOR]->(b:Disease {uid:$b}) '
                    'WHERE r.source="primekg" RETURN count(r) AS count',edge)[0]['count']
                if found:
                    edge['conflict'] = True
                    store.write('MATCH (a:Drug {uid:$a})-[r:INDICATED_FOR]->(b:Disease {uid:$b}) '
                        'WHERE r.source="primekg" SET r.conflict=true',edge)
        store.load([],[{k:v for k,v in e.items() if k!='quote'} for e in supported])
        write_lines(processed/'extracted_edges.jsonl',supported)
        caches = read_lines(processed/'extractions.jsonl')
        latest = {row['chunk_uid']:row for row in caches}
        for uid,row in latest.items():
            row['edges'] = [e for e in row['edges'] if uid in by_chunk and cached_edge_supported(e,by_chunk[uid],by_entity)]
            row['cache_validation_version'] = VERSION
            row.setdefault('error_type',None)
        write_lines(processed/'extractions.jsonl',list(latest.values()))
        review = ROOT/'eval/human_labels/extraction_repair_review_todo.jsonl'
        write_lines(review,[{'id':f'repair-{i+1:03d}',**e,'review_status':'quarantined',
            'reason':'Quote does not support both endpoints under the repaired catalog',
            'human_supported':None,'contexts':[by_chunk[uid] for uid in e['evidence'] if uid in by_chunk]}
            for i,e in enumerate(quarantined)])
        report.update(applied=True,mentions=len(linked),graph_counts=store.counts(),
            alias_vectors=len(json.loads((processed/'vector_aliases.json').read_text(encoding='utf8'))),
            corpus_rows=total,corpus_sha256=progress['sha256'],backup_directory=str(backup),
            quarantined_review_file=str(review))
        text_counts = json.loads((processed/'text_counts.json').read_text(encoding='utf8'))
        text_counts.update(openfda=stats,mentions=len(linked),graph_counts=report['graph_counts'],repair_version=report['repair_version'])
        (processed/'text_counts.json').write_text(json.dumps(text_counts,indent=2),encoding='utf8')
        summary_path.write_text(json.dumps(report,indent=2),encoding='utf8')
        print(json.dumps(report,indent=2))
    finally:
        store.close()


if __name__=='__main__':
    main()
