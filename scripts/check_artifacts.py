"""Read-only consistency checks for cached derived artifacts, without providers."""

import argparse
import hashlib
import json

import numpy as np

from medkg.config import ROOT
from medkg.ingest.extract import cached_edge_supported


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def lines(path):
    return [json.loads(line) for line in path.read_text(encoding='utf8').splitlines()]


def verify(root=ROOT):
    processed = root/'data/processed'
    entities = {e['uid']:e for e in json.loads((processed/'entities.json').read_text(encoding='utf8'))}
    documents = {d['uid']:d for d in lines(processed/'documents.jsonl')}
    chunks = {c['uid']:c for c in lines(processed/'chunks.jsonl')}
    edges = lines(processed/'extracted_edges.jsonl')
    aliases = json.loads((processed/'vector_aliases.json').read_text(encoding='utf8'))
    progress = json.loads((processed/'vector_progress.json').read_text(encoding='utf8'))
    manifest = json.loads((root/'eval/datasets/MANIFEST.json').read_text(encoding='utf8'))
    alias_vectors = np.load(processed/'alias_vectors.npy',mmap_mode='r')
    corpus_vectors = np.load(processed/'vector_corpus.npy',mmap_mode='r')
    try:
        checks = {
            'frozen_dataset':digest(root/'eval/datasets/structured_v1.jsonl')==manifest['dataset_sha256'],
            'corpus_hash':digest(processed/'vector_corpus.jsonl')==progress['sha256'],
            'alias_shape':alias_vectors.shape==(len(aliases),384),
            'alias_identities':all(a['uid'] in entities and a['text'] in
                [entities[a['uid']]['name'],*entities[a['uid']]['synonyms']] for a in aliases),
            'corpus_shape':corpus_vectors.shape==(progress['total'],384),
            'corpus_complete':progress['completed']==progress['total'],
            'chunk_associations':all(c['document_uid'] in documents and c.get('about',[])==
                documents[c['document_uid']].get('about',[]) for c in chunks.values()),
            'assertion_evidence':all(any(cached_edge_supported(e,chunks[uid],entities)
                for uid in e.get('evidence',[]) if uid in chunks) for e in edges),
        }
        return {'passed':all(checks.values()),'checks':checks,'retained_assertions':len(edges),
                'alias_rows':len(aliases),'corpus_rows':progress['total'],
                'graph_checked':False,'clinical_validation':False,'downloads':0,'llm_calls':0}
    finally:
        alias_vectors._mmap.close()
        corpus_vectors._mmap.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output')
    args = parser.parse_args()
    result = verify()
    if args.output:
        from pathlib import Path
        Path(args.output).write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps(result,indent=2))
    if not result['passed']:
        raise SystemExit(1)


if __name__=='__main__':
    main()
