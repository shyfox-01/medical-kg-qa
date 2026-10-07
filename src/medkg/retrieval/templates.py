"""Parameterized single-hop and count queries."""

SPECS = {
    'indications': ('Drug', 'Disease', 'INDICATED_FOR', False),
    'drugs_for': ('Disease', 'Drug', 'INDICATED_FOR', True),
    'side_effects': ('Drug', 'Phenotype', 'HAS_SIDE_EFFECT', False),
    'drugs_with_side_effect': ('Phenotype', 'Drug', 'HAS_SIDE_EFFECT', True),
    'phenotypes': ('Disease', 'Phenotype', 'HAS_PHENOTYPE', False),
    'contraindications': ('Drug', 'Disease', 'CONTRAINDICATED_FOR', False),
    'contraindicated_drugs': ('Disease', 'Drug', 'CONTRAINDICATED_FOR', True),
    'interactions': ('Drug', 'Drug', 'INTERACTS_WITH', None),
    'diseases_for': ('Phenotype', 'Disease', 'HAS_PHENOTYPE', True),
    'genes': ('Disease', 'Gene', 'ASSOCIATED_WITH', False),
    'targets': ('Drug', 'Gene', 'TARGETS', False),
    'parents': ('Disease', 'Disease', 'SUBTYPE_OF', False),
    'subtypes': ('Disease', 'Disease', 'SUBTYPE_OF', True),
    'off_label': ('Drug', 'Disease', 'OFF_LABEL_FOR', False),
    'off_label_drugs': ('Disease', 'Drug', 'OFF_LABEL_FOR', True),
    'targeting_drugs': ('Gene', 'Drug', 'TARGETS', True),
    'associated_diseases': ('Gene', 'Disease', 'ASSOCIATED_WITH', True),
}


def query(intent: str, uids: list[str], count: bool = False) -> tuple[str, dict]:
    if (intent not in SPECS or not isinstance(uids,list) or not uids or len(uids)>25
            or any(not isinstance(uid,str) or not uid for uid in uids)):
        raise ValueError('Template requires an allowed intent and anchor uid')
    uids = list(dict.fromkeys(uids))
    if intent=='interactions' and len(uids)>2:
        raise ValueError('Interactions require one anchor or exactly two drugs')
    source, target, relation, reverse = SPECS[intent]
    arrow = '<-[r:'+relation+']-' if reverse is True else '-[r:'+relation+']->'
    if reverse is None:
        arrow = '-[r:'+relation+']-'
    where = 'a.uid = $uid'
    params = {'uid':uids[0], 'other':uids[1] if len(uids)>1 else ''}
    if intent == 'interactions' and len(uids)>1:
        where += ' AND b.uid = $other'
    elif len(uids)>1:
        where = 'a.uid IN $uids'
        params['uids'] = uids
    result = ('count(DISTINCT b) AS count, collect(DISTINCT r.source) AS sources' if count else
              'DISTINCT b.uid AS uid, b.name AS name, b.synonyms AS synonyms, '
              'r.source AS source, r.kind AS kind, r.conflict AS conflict, r.evidence AS evidence, '
              'a.uid AS anchor_uid, a.name AS anchor_name')
    statement = f'MATCH (a:{source}){arrow}(b:{target}) WHERE {where} RETURN {result}'
    statement += ' LIMIT 25' if count else ' ORDER BY name LIMIT 25'
    return statement, params
