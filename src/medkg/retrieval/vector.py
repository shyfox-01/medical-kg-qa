import json

import numpy as np

from medkg.config import ROOT
from medkg.embeddings import Embeddings
from medkg.graph.store import QueryResult

EMBEDDER = Embeddings()
CORPUS = None
VECTORS = None


def search(store,query: str,source: str | None = None,uids: list[str] | None = None,
           mode: str = 'hybrid') -> QueryResult:
    global CORPUS,VECTORS
    embedding = EMBEDDER.encode([query])[0]
    if mode=='vector':
        directory = ROOT/'data/processed'
        if CORPUS is None:
            CORPUS = [json.loads(line) for line in (directory/'vector_corpus.jsonl').read_text(encoding='utf8').splitlines()]
            progress = json.loads((directory/'vector_progress.json').read_text(encoding='utf8'))
            if progress.get('completed')!=len(CORPUS) or progress.get('total')!=len(CORPUS):
                CORPUS = None
                raise RuntimeError('Pure-vector corpus embeddings are incomplete')
            VECTORS = np.load(directory/'vector_corpus.npy',mmap_mode='r')
            if VECTORS.shape!=(len(CORPUS),384):
                CORPUS = None
                raise RuntimeError('Pure-vector corpus shape mismatch')
        scores = VECTORS @ embedding
        rows = []
        for i in np.argsort(-scores):
            item = CORPUS[int(i)]
            if source and item['source']!=source:
                continue
            if uids and not set(item.get('about',[])) & set(uids):
                continue
            rows.append({**item,'score':float(scores[i])})
            if len(rows)==8:
                break
        return QueryResult(rows,'',False)
    if source and source not in ('medlineplus','openfda'):
        raise ValueError('Unknown document source')
    # k=8 is applied after filtering; widen ANN candidate pool for selective filters.
    rows = store.read("CALL db.index.vector.queryNodes('chunk_embedding',$pool,$embedding) "
        'YIELD node,score MATCH (d:Document)-[:HAS_CHUNK]->(node) '
        'WHERE ($source IS NULL OR d.source=$source) AND '
        '(size($uids)=0 OR EXISTS { MATCH (d)-[:ABOUT]->(entity) WHERE entity.uid IN $uids }) '
        'OPTIONAL MATCH (d)-[:ABOUT]->(entity) '
        'RETURN node.uid AS uid,node.text AS text,node.section AS section,d.source AS source, '
        'd.url AS url,d.title AS title,collect(DISTINCT entity.uid) AS entity_uids,score ORDER BY score DESC LIMIT 8',
        {'pool':512 if source or uids else 8,'embedding':embedding.tolist(),'source':source,'uids':uids or []})
    return QueryResult(rows,'',False)
