import json

import numpy as np

from medkg.config import ROOT, env
from medkg.embeddings import Embeddings, Reranker
from medkg.graph.store import QueryResult
from medkg.retrieval.fulltext import lucene

EMBEDDER = Embeddings()
RERANKER = Reranker()
CORPUS = None
VECTORS = None

# D115: the vector index and the English full-text (BM25) index each return up to
# CANDIDATES chunks under the same filters; reciprocal rank fusion keeps the TOP.
# With RERANK_MODEL set, a cross-encoder reorders the first CANDIDATES fused chunks
# instead. It is off by default: on the text set it raised the gold chunk to first
# place more often but not into the TOP, and added seconds per search on the CPU.
CANDIDATES = 30
TOP = 8
RRF_K = 60

CHUNK_ROWS = ('MATCH (d:Document)-[:HAS_CHUNK]->(node) '
              'WHERE ($source IS NULL OR d.source=$source) AND '
              '(size($uids)=0 OR EXISTS { MATCH (d)-[:ABOUT]->(entity) WHERE entity.uid IN $uids }) '
              'OPTIONAL MATCH (d)-[:ABOUT]->(entity) '
              'RETURN node.uid AS uid,node.text AS text,node.section AS section,d.source AS source, '
              'd.url AS url,d.title AS title,collect(DISTINCT entity.uid) AS entity_uids,score '
              'ORDER BY score DESC LIMIT $limit')


def dense(store,query: str,source: str | None = None,uids: list[str] | None = None,
          limit: int = CANDIDATES) -> list[dict]:
    """Chunks nearest to the query embedding; selective filters widen the ANN pool."""
    embedding = EMBEDDER.encode([query])[0]
    return store.read("CALL db.index.vector.queryNodes('chunk_embedding',$pool,$embedding) YIELD node,score "
                      +CHUNK_ROWS, {'pool':512 if source or uids else limit,'embedding':embedding.tolist(),
                                    'source':source,'uids':uids or [],'limit':limit})


def sparse(store,query: str,source: str | None = None,uids: list[str] | None = None,
           limit: int = CANDIDATES) -> list[dict]:
    """Chunks ranked by the full-text index for the query's words."""
    expression = lucene(query)
    if not expression:
        return []
    return store.read("CALL db.index.fulltext.queryNodes('ft_chunk_text',$query) YIELD node,score "+CHUNK_ROWS,
                      {'query':expression,'source':source,'uids':uids or [],'limit':limit})


def fuse(ranked_lists: list[list[dict]],top: int = TOP,k: int = RRF_K) -> list[dict]:
    """Reciprocal rank fusion: every list adds 1/(k+rank) to each chunk it returned.

    Ties keep the order of the first list (dense ranks come first)."""
    scores,rows = {},{}
    for ranked in ranked_lists:
        for rank,row in enumerate(ranked,1):
            scores[row['uid']] = scores.get(row['uid'],0.0)+1/(k+rank)
            rows.setdefault(row['uid'],row)
    order = sorted(scores,key=lambda uid: -scores[uid])[:top]
    return [{**rows[uid],'score':round(scores[uid],6)} for uid in order]


def rerank(query: str,rows: list[dict],model: str,top: int = TOP) -> list[dict]:
    """Reorder chunks by a cross-encoder reading the query with each chunk and its title."""
    if not rows:
        return rows
    scores = RERANKER.scores(model,query,[f"{row.get('title') or ''}. {row['text']}" for row in rows])
    order = sorted(range(len(rows)),key=lambda i: -scores[i])[:top]
    return [{**rows[i],'score':round(scores[i],4)} for i in order]


def search(store,query: str,source: str | None = None,uids: list[str] | None = None,
           mode: str = 'hybrid') -> QueryResult:
    global CORPUS,VECTORS
    if mode=='vector':
        embedding = EMBEDDER.encode([query])[0]
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
    model = env('RERANK_MODEL')
    rows = fuse([dense(store,query,source,uids),sparse(store,query,source,uids)],
                top=CANDIDATES if model else TOP)
    return QueryResult(rerank(query,rows,model) if model else rows,'',False)
