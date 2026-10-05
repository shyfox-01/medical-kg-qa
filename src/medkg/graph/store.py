"""Read-only QA transactions; trusted ingestion has a distinct write boundary."""

from dataclasses import dataclass
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
                rows = tx.run(verdict.stmt, params or {}).data()
                self.executed_statements.append(verdict.stmt)
                tx.commit()
        return QueryResult(rows, verdict.stmt, len(rows) >= verdict.limit, perf_counter()-started)

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

    def entities(self) -> list[dict]:
        return self.read('MATCH (n) WHERE any(l IN labels(n) WHERE l IN $labels) '
                         'RETURN n.uid AS uid, n.name AS name, n.synonyms AS synonyms, '
                         'labels(n)[0] AS label', {'labels': list(LABELS[:4])}, timeout=60)
