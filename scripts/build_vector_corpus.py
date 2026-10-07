"""Pure-vector control: all public text plus every retained PrimeKG entity relation."""

import argparse
import hashlib
import json
from collections import defaultdict

import numpy as np

from medkg.config import ROOT
from medkg.embeddings import Embeddings
from medkg.ingest.ontology import load_obo
from medkg.ingest.primekg import read_graph
from medkg_data.lexicon import normalize


def prioritized_synonyms(entity: dict, mesh_aliases: list[str], limit: int = 20) -> list[str]:
    """Use catalog aliases only, putting retained D049 MeSH additions first."""
    catalog = entity.get('synonyms') or []
    allowed = {normalize(alias) for alias in catalog}
    seen = {normalize(entity['name'])}
    selected = []
    for alias in [*mesh_aliases, *catalog]:
        key = normalize(alias)
        if key and key in allowed and key not in seen:
            selected.append(alias)
            seen.add(key)
            if len(selected) == limit:
                break
    return selected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--batch-size',type=int,default=64)
    parser.add_argument('--threads',type=int,choices=[1,2,3,4],default=2)
    parser.add_argument('--rebuild',action='store_true',
                        help='Regenerate all paragraphs; back up the existing corpus first')
    args = parser.parse_args()
    processed,raw = ROOT/'data/processed',ROOT/'data/raw'
    corpus = processed/'vector_corpus.jsonl'
    previous_digest = hashlib.sha256(corpus.read_bytes()).hexdigest() if corpus.exists() else None
    rebuilt = args.rebuild or not corpus.exists()
    if rebuilt:
        catalog = {e['uid']:e for e in json.loads((processed/'entities.json').read_text(encoding='utf8'))}
        mesh_aliases = defaultdict(list)
        additions = processed/'synonym_additions.jsonl'
        if additions.exists():
            for line in additions.read_text(encoding='utf8').splitlines():
                addition = json.loads(line)
                if addition['source'].startswith('mesh:'):
                    mesh_aliases[addition['uid']].append(addition['alias'])
        nodes,edges,_ = read_graph(raw/'kg.csv',load_obo(raw/'mondo.obo'),load_obo(raw/'hp.obo'))
        names = {n['uid']:n['name'] for n in nodes}
        facts = defaultdict(list)
        for edge in edges:
            sentence = f"{names[edge['a']]} {edge['type'].lower().replace('_',' ')} {names[edge['b']]} (PrimeKG)."
            facts[edge['a']].append(sentence)
            facts[edge['b']].append(sentence)
        building = corpus.with_suffix('.jsonl.rebuilding')
        with building.open('w',encoding='utf8') as stream:
            for line in (processed/'chunks.jsonl').read_text(encoding='utf8').splitlines():
                stream.write(line+'\n')
            for node in nodes:
                aliases = prioritized_synonyms(catalog[node['uid']],mesh_aliases[node['uid']])
                document = {'uid':'vector-primekg:'+node['uid'],'title':node['name'],
                            'source':'primekg','url':'https://doi.org/10.7910/DVN/IXA7BM','about':[node['uid']]}
                paragraph = (node['name']+'. Also known as: '+
                             (', '.join(aliases) or 'none recorded')+'. '+
                             ' '.join(facts[node['uid']]))
                stream.write(json.dumps({'uid':document['uid'],'name':document['title'],
                    'text':paragraph,'section':'graph_relations','source':'primekg',
                    'url':document['url'],'about':document['about']})+'\n')
        building.replace(corpus)
        del nodes,edges,facts,catalog,mesh_aliases
    rows = [json.loads(line) for line in corpus.read_text(encoding='utf8').splitlines()]
    seen = {r['uid'] for r in rows}
    missing = [json.loads(line) for line in (processed/'chunks.jsonl').read_text(encoding='utf8').splitlines()
               if json.loads(line)['uid'] not in seen]
    if missing:
        with corpus.open('a',encoding='utf8') as stream:
            for row in missing:
                stream.write(json.dumps(row)+'\n')
        rows.extend(missing)
    digest = hashlib.sha256(corpus.read_bytes()).hexdigest()
    progress = processed/'vector_progress.json'
    matrix = processed/'vector_corpus.npy'
    existing = json.loads(progress.read_text(encoding='utf8')) if progress.exists() else {}
    if existing.get('sha256')==digest and matrix.exists():
        vectors = np.lib.format.open_memmap(matrix,mode='r+')
        start = existing['completed']
    elif (not rebuilt and previous_digest is not None and
          existing.get('sha256')==previous_digest and matrix.exists()):
        old = np.load(matrix,mmap_mode='r')
        enlarged = processed/'vector_corpus_growing.npy'
        new = np.lib.format.open_memmap(enlarged,mode='w+',dtype=np.float32,shape=(len(rows),384))
        start = existing['completed']
        new[:start] = old[:start]
        new.flush()
        old._mmap.close()
        new._mmap.close()
        enlarged.replace(matrix)
        vectors = np.lib.format.open_memmap(matrix,mode='r+')
    else:
        vectors = np.lib.format.open_memmap(matrix,mode='w+',dtype=np.float32,shape=(len(rows),384))
        start = 0
    embedder = Embeddings(threads=args.threads)
    for i in range(start,len(rows),args.batch_size):
        batch = rows[i:i+args.batch_size]
        vectors[i:i+len(batch)] = embedder.encode([r['text'] for r in batch])
        vectors.flush()
        progress.write_text(json.dumps({'sha256':digest,'completed':i+len(batch),'total':len(rows)}),encoding='utf8')
        if i % 1024==0:
            print(f'Vector control embedded {i+len(batch)}/{len(rows)} chunks',flush=True)
    print(json.dumps({'corpus_chunks':len(rows),'completed':len(rows),'sha256':digest}))


if __name__=='__main__':
    main()
