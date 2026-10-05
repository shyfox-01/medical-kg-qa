"""Parameterized single-hop and count queries."""

SPECS = {
    'indications': ('Drug', 'Disease', 'INDICATED_FOR', False),
    'drugs_for': ('Disease', 'Drug', 'INDICATED_FOR', True),
    'side_effects': ('Drug', 'Phenotype', 'HAS_SIDE_EFFECT', False),
    'phenotypes': ('Disease', 'Phenotype', 'HAS_PHENOTYPE', False),
    'contraindications': ('Drug', 'Disease', 'CONTRAINDICATED_FOR', False),
    'contraindicated_drugs': ('Disease', 'Drug', 'CONTRAINDICATED_FOR', True),
    'interactions': ('Drug', 'Drug', 'INTERACTS_WITH', None),
    'diseases_for': ('Phenotype', 'Disease', 'HAS_PHENOTYPE', True),
    'genes': ('Disease', 'Gene', 'ASSOCIATED_WITH', False),
    'targets': ('Drug', 'Gene', 'TARGETS', False),
}


def query(intent: str, uids: list[str], count: bool = False) -> tuple[str, dict]:
    if intent not in SPECS or not uids:
        raise ValueError('Template requires an allowed intent and anchor uid')
    source, target, relation, reverse = SPECS[intent]
    arrow = '<-[r:'+relation+']-' if reverse is True else '-[r:'+relation+']->'
    if reverse is None:
        arrow = '-[r:'+relation+']-'
    where = 'a.uid = $uid'
    if intent == 'interactions' and len(uids)>1:
        where += ' AND b.uid = $other'
    result = ('count(DISTINCT b) AS count, collect(DISTINCT r.source) AS sources' if count else
              'DISTINCT b.uid AS uid, b.name AS name, b.synonyms AS synonyms, '
              'r.source AS source, r.conflict AS conflict, r.evidence AS evidence')
    statement = f'MATCH (a:{source}){arrow}(b:{target}) WHERE {where} RETURN {result}'
    statement += ' LIMIT 25' if count else ' ORDER BY name LIMIT 25'
    return statement, {'uid':uids[0], 'other':uids[1] if len(uids)>1 else ''}
