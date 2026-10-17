"""Truncated PrimeKG group labels do not shadow the entity of that name (D088), fictional entities only."""

from medkg.qa.linker import Linker
from medkg.qa.router import route

ENTITIES = [
    {'uid':'fiction:orion','label':'Disease','name':'Orion fever','synonyms':[]},
    {'uid':'MONDO_grouped:1_2','label':'Disease','name':'Orion fever,','synonyms':['Orion fever type 1']},
    {'uid':'fiction:orion-p','label':'Phenotype','name':'Orion fever','synonyms':[]},
    {'uid':'MONDO_grouped:3_4','label':'Disease','name':'Lyra disease,','synonyms':[]},
]


def test_truncated_group_label_does_not_make_a_name_ambiguous():
    linker = Linker(ENTITIES)
    question = 'Which drugs can cause Orion fever?'
    candidates,unresolved = linker.question_mentions(question)
    assert 'MONDO_grouped:1_2' not in {c.uid for c in candidates} and not unresolved
    assert route(question,candidates)=='drugs_with_side_effect'


def test_group_remains_reachable_by_subtype_names_and_unshadowed_labels():
    linker = Linker(ENTITIES)
    assert [c.uid for c in linker.in_question('What are the symptoms of Orion fever type 1?')]==['MONDO_grouped:1_2']
    assert [c.uid for c in linker.in_question('What are the symptoms of Lyra disease?')]==['MONDO_grouped:3_4']


def test_drugs_that_cause_a_disease_are_never_answered_with_its_treatments():
    linker = Linker(ENTITIES)
    for question in ('Which drugs cause Lyra disease?','What medications can induce Lyra disease?'):
        assert route(question,linker.in_question(question)) is None
    assert route('Which drugs treat Lyra disease?',linker.in_question('Which drugs treat Lyra disease?'))=='drugs_for'
