import re

from medkg.graph.schema import LABELS
from medkg.graph.store import QueryResult


def search(store,query: str,label: str = 'Disease') -> QueryResult:
    if label not in LABELS:
        raise ValueError('Unknown fulltext label')
    terms = re.findall(r'[A-Za-z0-9]+',query)[:20]
    lucene = ' OR '.join('"'+t+'"' for t in terms)
    rows = store.read('CALL db.index.fulltext.queryNodes($index,$query) YIELD node,score '
                     'OPTIONAL MATCH (d:Document)-[:HAS_CHUNK]->(node) '
                     'RETURN node.uid AS uid,node.name AS name,node.text AS text, '
                     'node.section AS section,coalesce(node.url,d.url) AS url,'
                     'coalesce(node.source,d.source,split(node.uid,":")[0]) AS source,score LIMIT 8',
                     {'index':'ft_chunk_text' if label=='Chunk' else 'ft_'+label,'query':lucene}) if terms else []
    return QueryResult(rows,'',len(rows)>=8)
