"""Catalog audit finds review candidates without making human decisions."""

import copy

from scripts.audit_aliases import audit


def test_collisions_and_unreproduced_sources_are_reported_without_mutation():
    entities = [
        {'uid':'d:a','label':'Drug','name':'Asterol','synonyms':['Sharedbrand','CLASS']},
        {'uid':'d:b','label':'Drug','name':'Brinex','synonyms':['Sharedbrand']},
        {'uid':'p:a','label':'Phenotype','name':'Fictional marks','synonyms':['CLASS']},
    ]
    before = copy.deepcopy(entities)
    additions = [{'uid':'d:a','alias':'CLASS','source':'mesh:D999'}]
    rows = audit(entities,additions,set())
    assert entities==before
    suspicious = next(r for r in rows if r['uid']=='d:a' and r['alias_key']=='class')
    assert {'mesh_join_not_reproduced','acronym_collision'}<=set(suspicious['flags'])
    assert suspicious['unreproduced_source_ids']==['mesh:D999']
    assert all('decision' not in r for r in rows)
    assert sum('same_label_collision' in r['flags'] for r in rows)==2


def test_same_name_disease_and_phenotype_pair_is_not_an_unrelated_collision():
    entities = [
        {'uid':'d:a','label':'Disease','name':'Orion syndrome (disease)','synonyms':['Star syndrome']},
        {'uid':'p:a','label':'Phenotype','name':'Orion syndrome','synonyms':['Star syndrome']},
    ]
    assert audit(entities,[],set())==[]


def test_supported_source_is_not_flagged_but_word_collision_remains_visible():
    entities = [{'uid':'d:a','label':'Drug','name':'Asterol','synonyms':['Starbrand','LET']}]
    additions = [{'uid':'d:a','alias':'Starbrand','source':'mesh:D1'}]
    rows = audit(entities,additions,{('d:a','starbrand','mesh:D1')})
    assert len(rows)==1 and rows[0]['forms']==['LET']
    assert rows[0]['flags']==['ordinary_or_generic_word']
