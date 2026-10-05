from medkg.graph.store import QueryResult


def search(store,uids: list[str],hops: int = 2) -> QueryResult:
    if hops not in (1,2) or len(uids)>25:
        raise ValueError('Expansion permits at most 25 anchors and two hops')
    rows = store.read('MATCH (a) WHERE a.uid IN $uids WITH a LIMIT 25 '
        f'MATCH p=(a)-[:INDICATED_FOR|CONTRAINDICATED_FOR|OFF_LABEL_FOR|INTERACTS_WITH|HAS_SIDE_EFFECT|HAS_PHENOTYPE|ASSOCIATED_WITH|TARGETS|SUBTYPE_OF|MENTIONS|ABOUT|HAS_CHUNK*1..{hops}]-(b) '
        'RETURN DISTINCT b.uid AS uid,b.name AS name, '
        '[r IN relationships(p) WHERE r.source IS NOT NULL | r.source] AS sources LIMIT 26',{'uids':uids})
    return QueryResult(rows[:25],'',len(rows)>25)
