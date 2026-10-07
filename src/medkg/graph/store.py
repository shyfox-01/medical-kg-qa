"""Read-only QA transactions; trusted ingestion has a distinct write boundary."""

from dataclasses import dataclass
from itertools import islice
from time import perf_counter

from neo4j import READ_ACCESS, GraphDatabase

from medkg.config import Settings
from medkg.graph.guard import CypherRejected, check
from medkg.graph.schema import LABELS, RELATIONS, statements


@dataclass
class QueryResult:
    rows: list[dict]
    stmt: str
    truncated: bool = False
    seconds: float = 0


class GraphStore:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()
        self.settings.require()
        self.executed_statements = []
        self.driver = GraphDatabase.driver(self.settings.neo4j_uri,
            auth=(self.settings.neo4j_user, self.settings.neo4j_password))

    def close(self) -> None:
        self.driver.close()

    def verify(self) -> None:
        self.driver.verify_connectivity()

    def read(self, statement: str, params: dict | None = None, timeout: float | None = None) -> list[dict]:
        self.executed_statements.append(statement)
        with self.driver.session(database=self.settings.neo4j_database,
                                 default_access_mode=READ_ACCESS) as session:
            with session.begin_transaction(timeout=timeout or self.settings.query_timeout) as tx:
                rows = tx.run(statement, params or {}).data()
                tx.commit()
                return rows

    def write(self, statement: str, params: dict | None = None) -> list[dict]:
        with self.driver.session(database=self.settings.neo4j_database) as session:
            return session.execute_write(lambda tx: tx.run(statement, params or {}).data())

    def run_generated(self, cypher: str, params: dict | None = None) -> QueryResult:
        verdict = check(cypher, self.settings.max_limit, 25, self.settings.max_hops)
        started = perf_counter()
        with self.driver.session(database=self.settings.neo4j_database,
                                 default_access_mode=READ_ACCESS) as session:
            with session.begin_transaction(timeout=self.settings.query_timeout) as tx:
                summary = tx.run('EXPLAIN ' + verdict.stmt, params or {}).consume()
                for note in summary.notifications or []:
                    if any(x in note.get('code', '') for x in
                           ('UnknownLabel', 'UnknownRelationshipType')):
                        raise CypherRejected('EXPLAIN reports an unknown schema element')
                cursor = tx.run(verdict.stmt, params or {})
                rows = [record.data() for record in islice(cursor,verdict.limit)]
                overflow = cursor.peek() is not None
                self.executed_statements.append(verdict.stmt)
                tx.commit()
        return QueryResult(rows, verdict.stmt, overflow or len(rows)>=verdict.limit,
                           perf_counter()-started)

    def create_schema(self) -> None:
        for stmt in statements():
            self.write(stmt)

    def load(self, nodes: list[dict], edges: list[dict], batch_size: int = 10000) -> None:
        for label in LABELS:
            batch = [{k: v for k, v in n.items() if k not in ('label', 'node_id')}
                     for n in nodes if n['label'] == label]
            for i in range(0, len(batch), batch_size):
                self.write(f'UNWIND $rows AS row MERGE (n:{label} {{uid: row.uid}}) SET n += row',
                           {'rows': batch[i:i+batch_size]})
        for rel in RELATIONS:
            batch = [e for e in edges if e['type'] == rel]
            endpoints = {
                'INDICATED_FOR': ('Drug','Disease'), 'CONTRAINDICATED_FOR': ('Drug','Disease'),
                'OFF_LABEL_FOR': ('Drug','Disease'), 'INTERACTS_WITH': ('Drug','Drug'),
                'HAS_SIDE_EFFECT': ('Drug','Phenotype'), 'HAS_PHENOTYPE': ('Disease','Phenotype'),
                'ASSOCIATED_WITH': ('Disease','Gene'), 'TARGETS': ('Drug','Gene'),
                'SUBTYPE_OF': ('Disease','Disease'),
            }
            if not batch:
                continue
            left, right = endpoints[rel]
            key = 'source: row.source, kind: row.props.kind' if rel=='TARGETS' else 'source: row.source'
            for i in range(0, len(batch), batch_size):
                self.write(f'UNWIND $rows AS row MATCH (a:{left} {{uid: row.a}}), (b:{right} {{uid: row.b}}) '
                           f'MERGE (a)-[r:{rel} {{{key}}}]->(b) '
                           'SET r += row.props',
                           {'rows': [{'a': e['a'], 'b': e['b'], 'source': e['source'],
                                      'props': {k: v for k, v in e.items() if k not in ('a','b','type')}}
                                     for e in batch[i:i+batch_size]]})

    def counts(self) -> dict:
        return {'nodes': {r['label']: r['count'] for r in self.read(
                    'MATCH (n) RETURN labels(n)[0] AS label, count(*) AS count', timeout=60)},
                'relations': {r['type']: r['count'] for r in self.read(
                    'MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS count', timeout=60)}}

    def reconcile_extracted(self, selected: set[str], retained: list[dict]) -> None:
        """Replace selected FDA evidence and conflict flags in one transaction."""
        from medkg.ingest.reconcile import reconcile_edges
        allowed = {'CONTRAINDICATED_FOR','INTERACTS_WITH'}
        if any(e['type'] not in allowed or e['source']!='openfda_extracted' or
               not set(e.get('evidence',[]))<=selected for e in retained):
            raise ValueError('Reconciliation requires selected FDA assertions')
        with self.driver.session(database=self.settings.neo4j_database) as session:
            with session.begin_transaction(timeout=60) as tx:
                old = tx.run('MATCH (a)-[r]->(b) WHERE r.source="openfda_extracted" '
                    'AND (any(uid IN r.evidence WHERE uid IN $selected) OR '
                    'any(key IN $keys WHERE a.uid=key.a AND b.uid=key.b AND type(r)=key.type)) '
                    'RETURN a.uid AS a,b.uid AS b,type(r) AS type,properties(r) AS props',
                    {'selected':sorted(selected),'keys':[{'a':e['a'],'b':e['b'],'type':e['type']}
                                                        for e in retained]}).data()
                existing = [{**r['props'],'a':r['a'],'b':r['b'],'type':r['type']} for r in old]
                updated = reconcile_edges(existing,selected,retained)
                touched = {(e['a'],e['b'],e['type']) for e in [*existing,*retained]}
                for relation in sorted(allowed):
                    keys = [{'a':a,'b':b} for a,b,t in sorted(touched) if t==relation]
                    tx.run('UNWIND $rows AS row MATCH (a:Drug {uid:row.a})-[r:'+relation+
                        ']->(b {uid:row.b}) WHERE r.source="openfda_extracted" DELETE r',
                        {'rows':keys}).consume()
                    rows = [{**e,'props':{k:v for k,v in e.items() if k not in
                             ('a','b','type','quote')}} for e in updated if e['type']==relation]
                    tx.run('UNWIND $rows AS row MATCH (a:Drug {uid:row.a}),(b {uid:row.b}) '
                        'MERGE (a)-[r:'+relation+' {source:"openfda_extracted"}]->(b) '
                        'SET r += row.props',{'rows':rows}).consume()
                pairs = [{'a':a,'b':b} for a,b,t in sorted(touched) if t=='CONTRAINDICATED_FOR']
                tx.run('UNWIND $rows AS row MATCH (a:Drug {uid:row.a}),(b:Disease {uid:row.b}) '
                    'MATCH (a)-[r:INDICATED_FOR]->(b) WHERE r.source="primekg" '
                    'SET r.conflict=EXISTS { MATCH (a)-[:CONTRAINDICATED_FOR]->(b) }',
                    {'rows':pairs}).consume()
                tx.run('UNWIND $rows AS row MATCH (a:Drug {uid:row.a})'
                    '-[r:CONTRAINDICATED_FOR]->(b:Disease {uid:row.b}) '
                    'WHERE r.source="openfda_extracted" SET r.conflict=EXISTS {'
                    ' MATCH (a)-[i:INDICATED_FOR]->(b) WHERE i.source="primekg" }',
                    {'rows':pairs}).consume()
                tx.commit()

    def entities(self) -> list[dict]:
        return self.read('MATCH (n) WHERE any(l IN labels(n) WHERE l IN $labels) '
                         'RETURN n.uid AS uid, n.name AS name, n.synonyms AS synonyms, '
                         'labels(n)[0] AS label', {'labels': list(LABELS[:4])}, timeout=60)
