"""Canonical selection shared by ingestion and the CSV-only evaluation generator."""

import csv
from collections import Counter
from pathlib import Path

from medkg.ingest.ontology import Term, mondo_ids, orientation

TYPES = {'disease': 'Disease', 'drug': 'Drug', 'effect/phenotype': 'Phenotype',
         'gene/protein': 'Gene'}
MAPPING = {
    'indication': ('Drug', 'Disease', 'INDICATED_FOR'),
    'contraindication': ('Drug', 'Disease', 'CONTRAINDICATED_FOR'),
    'off-label use': ('Drug', 'Disease', 'OFF_LABEL_FOR'),
    'drug_drug': ('Drug', 'Drug', 'INTERACTS_WITH'),
    'drug_effect': ('Drug', 'Phenotype', 'HAS_SIDE_EFFECT'),
    'disease_phenotype_positive': ('Disease', 'Phenotype', 'HAS_PHENOTYPE'),
    'disease_protein': ('Disease', 'Gene', 'ASSOCIATED_WITH'),
    'drug_protein': ('Drug', 'Gene', 'TARGETS'),
    'disease_disease': ('Disease', 'Disease', 'SUBTYPE_OF'),
}


def node(row: dict, side: str) -> dict:
    source, identifier = row[f'{side}_source'], row[f'{side}_id']
    if identifier.endswith('.0'):
        identifier = identifier[:-2]
    return {'uid': f'{source}:{identifier}', 'node_id': identifier,
            'name': row[f'{side}_name'], 'label': TYPES.get(row[f'{side}_type'], ''),
            'synonyms': []}


def canonical_edge(row: dict, mondo: dict[str, Term]) -> tuple[dict, dict, dict] | None:
    relation = row['relation']
    if relation not in MAPPING:
        return None
    left, right, output = MAPPING[relation]
    a, b = node(row, 'x'), node(row, 'y')
    if (a['label'], b['label']) == (right, left) and left != right:
        a, b = b, a
    if (a['label'], b['label']) != (left, right):
        return None
    if output == 'INTERACTS_WITH' and a['uid'] > b['uid']:
        a, b = b, a
    if output == 'SUBTYPE_OF':
        direction = orientation(a['node_id'], b['node_id'], mondo)
        if direction is None:
            return None
        if direction[0] == b['node_id']:
            a, b = b, a
    edge = {'a': a['uid'], 'b': b['uid'], 'type': output, 'source': 'primekg', 'conflict': False}
    if output == 'TARGETS':
        edge['kind'] = row['display_relation']
    return a, b, edge


def read_graph(path: Path, mondo: dict[str, Term], hp: dict[str, Term]) -> tuple[list, list, dict]:
    nodes, edges, seen = {}, [], set()
    stats = Counter()
    raw_relations = Counter()
    for row in csv.DictReader(path.open(encoding='utf8', newline='')):
        raw_relations[row['relation']] += 1
        stats['csv_rows'] += 1
        item = canonical_edge(row, mondo)
        if item is None:
            stats['excluded_rows'] += 1
            continue
        a, b, edge = item
        key = (edge['a'], edge['b'], edge['type'], edge.get('kind', ''))
        if key in seen:
            stats['duplicate_or_reciprocal_rows'] += 1
            continue
        seen.add(key)
        edges.append(edge)
        nodes[a['uid']] = a
        nodes[b['uid']] = b
    for n in nodes.values():
        terms = []
        if n['label'] == 'Disease':
            terms = [mondo[x] for x in mondo_ids(n['node_id']) if x in mondo]
        elif n['label'] == 'Phenotype':
            key = 'HP:' + n['node_id'].removeprefix('HP:').zfill(7)
            terms = [hp[key]] if key in hp else []
        n['synonyms'] = sorted({s for t in terms for s in [t.name, *t.synonyms]} - {n['name']})
    report = {**stats, 'raw_relations': dict(raw_relations),
              'nodes': dict(Counter(n['label'] for n in nodes.values())),
              'relations': dict(Counter(e['type'] for e in edges))}
    return list(nodes.values()), edges, report
