"""Bounded neighborhood expansion that keeps relationship type and direction.

Every row states which relationship connects the anchor and the neighbor, so the
answer model cannot present a contraindication or side effect as an indication.
One-hop expansion samples each relationship type separately, so the 1.3M
INTERACTS_WITH edges cannot crowd out indications and contraindications.
"""

from collections import Counter

from medkg.graph.store import QueryResult

RELATIONS = ('INDICATED_FOR', 'CONTRAINDICATED_FOR', 'OFF_LABEL_FOR', 'HAS_SIDE_EFFECT',
             'HAS_PHENOTYPE', 'ASSOCIATED_WITH', 'TARGETS', 'SUBTYPE_OF', 'INTERACTS_WITH',
             'ABOUT', 'MENTIONS', 'HAS_CHUNK')
PER_RELATION = 4
MAX_ROWS = 48


def search(store,uids: list[str],hops: int = 2) -> QueryResult:
    if hops not in (1,2) or len(uids)>25:
        raise ValueError('Expansion permits at most 25 anchors and two hops')
    if hops==1:
        rows = store.read('MATCH (a) WHERE a.uid IN $uids WITH a LIMIT 25 '
            'UNWIND $relations AS relation '
            'CALL (a, relation) { MATCH (a)-[r]-(b) WHERE type(r) = relation '
            'RETURN r, b LIMIT $per_relation } '
            'RETURN a.uid AS anchor_uid, type(r) AS relation, '
            'CASE WHEN startNode(r) = a THEN a.name ELSE coalesce(b.name, b.title, b.uid) END AS subject, '
            'CASE WHEN startNode(r) = a THEN coalesce(b.name, b.title, b.uid) ELSE a.name END AS object, '
            'b.uid AS uid, coalesce(b.name, b.title, b.uid) AS name, r.source AS source, '
            'r.kind AS kind, r.conflict AS conflict, r.evidence AS evidence LIMIT $limit',
            {'uids':uids,'relations':list(RELATIONS),'per_relation':PER_RELATION,'limit':MAX_ROWS+1})
        groups = Counter((row['anchor_uid'],row['relation']) for row in rows)
        truncated = len(rows)>MAX_ROWS or any(n>=PER_RELATION for n in groups.values())
        return QueryResult(rows[:MAX_ROWS],'',truncated)
    rows = store.read('MATCH (a) WHERE a.uid IN $uids WITH a LIMIT 25 '
        'MATCH p=(a)-[:'+'|'.join(RELATIONS)+'*1..2]-(b) '
        'RETURN DISTINCT a.uid AS anchor_uid, b.uid AS uid, coalesce(b.name, b.title, b.uid) AS name, '
        '[r IN relationships(p) | {relation: type(r), '
        'subject: coalesce(startNode(r).name, startNode(r).uid), '
        'object: coalesce(endNode(r).name, endNode(r).uid), source: r.source}] AS path, '
        '[r IN relationships(p) WHERE r.source IS NOT NULL | r.source] AS sources LIMIT 26',
        {'uids':uids})
    return QueryResult(rows[:25],'',len(rows)>25)
