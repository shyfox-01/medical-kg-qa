"""Refresh alias-only corpus changes using the same cached embedding model.

Use only after synonym enrichment, with its backed-up previous catalog. All
relations, documents, ids and the embedding recipe must remain unchanged. A full
builder rebuild is required for other changes. No benchmark files are read.
"""

import argparse
import hashlib
import json
import os
import shutil
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from medkg.config import ROOT
from medkg.embeddings import Embeddings
from scripts.build_vector_corpus import prioritized_synonyms


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def refresh(processed: Path, previous: Path, backup: Path, embedder) -> dict:
    old = {e['uid']:e for e in json.loads(previous.read_text(encoding='utf8'))}
    new = {e['uid']:e for e in json.loads((processed/'entities.json').read_text(encoding='utf8'))}
    if old.keys()!=new.keys() or any(
        {k:v for k,v in old[uid].items() if k!='synonyms'}!=
        {k:v for k,v in new[uid].items() if k!='synonyms'} or
        not set(old[uid].get('synonyms',[]))<=set(new[uid].get('synonyms',[])) for uid in old):
        raise ValueError('Only synonym additions may use this refresh')
    corpus, matrix, progress = [processed/name for name in
        ('vector_corpus.jsonl','vector_corpus.npy','vector_progress.json')]
    state = json.loads(progress.read_text(encoding='utf8'))
    raw = corpus.read_bytes().splitlines(keepends=True)
    if state['sha256']!=digest(corpus) or state['completed']!=len(raw) or state['total']!=len(raw):
        raise ValueError('A complete hash-matched corpus is required')
    mesh = defaultdict(list)
    for line in (processed/'synonym_additions.jsonl').read_text(encoding='utf8').splitlines():
        entry = json.loads(line)
        if entry['source'].startswith('mesh:'):
            mesh[entry['uid']].append(entry['alias'])
    def prefix(entity):
        aliases = prioritized_synonyms(entity,mesh[entity['uid']])
        return entity['name']+'. Also known as: '+(', '.join(aliases) or 'none recorded')+'. '
    changed, texts, seen = [], [], set()
    for i,line in enumerate(raw):
        row = json.loads(line)
        if row['uid'] in seen:
            raise ValueError('Duplicate corpus uid')
        seen.add(row['uid'])
        if not row['uid'].startswith('vector-primekg:'):
            continue
        uid = row['uid'].removeprefix('vector-primekg:')
        before, after = prefix(old[uid]), prefix(new[uid])
        if not row['text'].startswith(before):
            raise ValueError('Previous alias paragraph does not match the supplied catalog')
        if before!=after:
            row['text'] = after+row['text'][len(before):]
            ending = '\r\n' if line.endswith(b'\r\n') else '\n'
            raw[i] = (json.dumps(row)+ending).encode('utf8')
            changed.append(i)
            texts.append(row['text'])
    with matrix.open('rb') as stream:
        # Validate the complete matrix before making any replacements.
        vectors = np.load(stream)
    if vectors.shape!=(len(raw),384) or vectors.dtype!=np.float32 or not np.isfinite(vectors).all():
        raise ValueError('Invalid source embedding matrix')
    backup.mkdir(parents=True,exist_ok=False)
    hashes = {}
    for path in (corpus,matrix,progress):
        shutil.copy2(path,backup/path.name)
        hashes[path.name] = digest(path)
        if digest(backup/path.name)!=hashes[path.name]:
            raise RuntimeError('Backup verification failed')
    for start in range(0,len(changed),32):
        batch = embedder.encode(texts[start:start+32])
        if batch.shape!=(len(changed[start:start+32]),384) or not np.isfinite(batch).all():
            raise ValueError('Invalid refreshed embeddings')
        vectors[changed[start:start+32]] = batch
    # Staging files are retained for recovery if interrupted before replacement.
    pending = backup/'prepared'
    pending.mkdir()
    (pending/corpus.name).write_bytes(b''.join(raw))
    np.save(pending/matrix.name,vectors)
    updated = {**state,'sha256':digest(pending/corpus.name)}
    (pending/progress.name).write_text(json.dumps(updated),encoding='utf8')
    report = {'changed_rows':len(changed),'reused_rows':len(raw)-len(changed),
              'rows':len(raw),'previous_hashes':hashes,'corpus_sha256':updated['sha256'],
              'embedding_model':'BAAI/bge-small-en-v1.5','downloads':0}
    (backup/'refresh.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    for path in (corpus,matrix,progress):
        (pending/path.name).replace(path)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--previous-catalog',type=Path,required=True)
    args = parser.parse_args()
    previous = args.previous_catalog.resolve()
    if not previous.is_relative_to(ROOT):
        raise ValueError('Previous catalog must be inside the repository')
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    report = refresh(ROOT/'data/processed',previous,
                     ROOT/'.cache'/f'synonym-corpus-{time.time_ns()}',Embeddings(threads=2))
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
