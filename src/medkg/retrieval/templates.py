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


# What the rows of each template are, in words. Some answer models do not infer this
# from Cypher and parameters (they reported "no drugs for both A and B" over rows that
# were exactly that intersection); D085.
PHRASES = {
    'indications': 'diseases for which {a} is indicated',
    'drugs_for': 'drugs indicated for {a}',
    'side_effects': 'side effects (phenotypes) recorded for {a}',
    'drugs_with_side_effect': 'drugs that have {a} as a recorded side effect',
    'phenotypes': 'phenotypes (symptoms and clinical features) of {a}',
    'contraindications': 'diseases in which {a} is contraindicated',
    'contraindicated_drugs': 'drugs contraindicated in {a}',
    'interactions': 'drugs that interact with {a}',
    'diseases_for': 'diseases that have {a} as a phenotype',
    'genes': 'genes associated with {a}',
    'targets': 'genes or proteins targeted by {a}',
    'parents': 'parent disease classes of {a}',
    'subtypes': 'subtypes of {a}',
    'off_label': 'diseases for which {a} is used off-label',
    'off_label_drugs': 'drugs used off-label for {a}',
    'targeting_drugs': 'drugs that target {a}',
    'associated_diseases': 'diseases associated with {a}',
}


# A pair check (D112): one drug and the disease or phenotype the question names.
PAIR_PHRASES = {
    'indications': 'the recorded indication of {a} for {b}, if any',
    'contraindications': 'the recorded contraindication of {a} in {b}, if any',
    'off_label': 'the recorded off-label use of {a} for {b}, if any',
    'side_effects': '{b}, if it is a recorded side effect of {a}',
}


# The verdict of a pair check, stated in code: the answer model denied returned rows.
PAIR_VERDICTS = {
    'indications': ('{a}', 'indicated for {b}'),
    'contraindications': ('{a}', 'contraindicated in {b}'),
    'off_label': ('{a}', 'used off-label for {b}'),
    'side_effects': ('{b}', 'a side effect of {a}'),
}


def pair_verdict(intent: str, anchor: str, target: str, recorded: bool) -> str:
    subject, predicate = (part.format(a=anchor, b=target) for part in PAIR_VERDICTS[intent])
    # No bare "Yes": the graph records a relation; it does not advise a person.
    if recorded:
        return f'The knowledge graph records {subject} as {predicate}.'
    return f'{subject[0].upper()}{subject[1:]} is not recorded as {predicate} in the knowledge graph.'


def describe(intent: str, names: list[str], count: bool = False, shared: bool = False,
             target: str | None = None) -> str:
    """One sentence stating what a template query's rows are."""
    if target and intent in PAIR_PHRASES:
        return 'The rows are ' + PAIR_PHRASES[intent].format(a=names[0], b=target) + '.'
    if len(names) > 3:
        anchors = f'{len(names)} entities retrieved by an earlier step'
    else:
        anchors = names[0] if len(names) == 1 else ', '.join(names[:-1]) + ' and ' + names[-1]
    if intent == 'interactions' and len(names) == 2 and not shared:
        phrase = f'the recorded interaction between {names[0]} and {names[1]}, if any'
    else:
        if shared:
            anchors = 'every one of ' + anchors + ' (each row is linked to all of them)'
        elif len(names) > 1:
            anchors = 'any of ' + anchors
        phrase = PHRASES[intent].format(a=anchors)
    return ('The rows give the number of ' if count else 'The rows are ') + phrase + '.'


def query(intent: str, uids: list[str], count: bool = False, shared: bool = False,
          target: str | None = None) -> tuple[str, dict]:
    """Parameterized relation lookup from one or more anchors.

    With several anchors the default is a union. shared=True returns only targets
    connected to every anchor ("drugs indicated for both A and B"), never an anchor
    itself; generated Cypher for these intersections often failed to parse (D082).
    target limits the result to one entity: a yes/no pair check (D112).
    """
    if (intent not in SPECS or not isinstance(uids,list) or not uids or len(uids)>25
            or any(not isinstance(uid,str) or not uid for uid in uids)):
        raise ValueError('Template requires an allowed intent and anchor uid')
    uids = list(dict.fromkeys(uids))
    source, label, relation, reverse = SPECS[intent]
    arrow = '<-[r:'+relation+']-' if reverse is True else '-[r:'+relation+']->'
    if reverse is None:
        arrow = '-[r:'+relation+']-'
    if shared:
        return _shared(source, label, arrow, uids, count)
    if intent=='interactions' and len(uids)>2:
        raise ValueError('Interactions require one anchor or exactly two drugs')
    if target is not None and (intent not in PAIR_PHRASES or len(uids)!=1 or not isinstance(target,str) or not target):
        raise ValueError('A pair check needs one anchor and one target uid')
    where = 'a.uid = $uid'
    params = {'uid':uids[0], 'other':uids[1] if len(uids)>1 else ''}
    if intent == 'interactions' and len(uids)>1:
        where += ' AND b.uid = $other'
    elif target is not None:
        where += ' AND b.uid = $target'
        params['target'] = target
    elif len(uids)>1:
        where = 'a.uid IN $uids'
        params['uids'] = uids
    result = ('count(DISTINCT b) AS count, collect(DISTINCT r.source) AS sources' if count else
              'DISTINCT b.uid AS uid, b.name AS name, b.synonyms AS synonyms, '
              'r.source AS source, r.kind AS kind, r.conflict AS conflict, r.evidence AS evidence, '
              'a.uid AS anchor_uid, a.name AS anchor_name')
    statement = f'MATCH (a:{source}){arrow}(b:{label}) WHERE {where} RETURN {result}'
    statement += ' LIMIT 25' if count else ' ORDER BY name LIMIT 25'
    return statement, params


def _shared(source: str, target: str, arrow: str, uids: list[str], count: bool) -> tuple[str, dict]:
    if len(uids) < 2:
        raise ValueError('Shared targets need at least two anchors')
    statement = (f'MATCH (a:{source}){arrow}(b:{target}) WHERE a.uid IN $uids AND NOT b.uid IN $uids '
                 'WITH b, collect(DISTINCT a.uid) AS anchor_uids, collect(DISTINCT r.source) AS sources, '
                 'max(CASE WHEN r.conflict THEN 1 ELSE 0 END) AS flagged '
                 'WHERE size(anchor_uids) = size($uids) ')
    if count:
        statement += 'RETURN count(b) AS count LIMIT 25'
    else:
        statement += ('RETURN b.uid AS uid, b.name AS name, b.synonyms AS synonyms, sources, '
                      'flagged = 1 AS conflict, anchor_uids ORDER BY name LIMIT 25')
    return statement, {'uids': uids}
