"""Fictional drug spelling families and ambiguity boundaries."""

import pytest

from medkg.qa.linker import Linker, label_choices
from medkg.qa.router import route

ENTITIES = [
    {'uid':'fiction:a','label':'Drug','name':'Asteramine','synonyms':['Asteramine brand']},
    {'uid':'fiction:b','label':'Drug','name':'Brinexamine','synonyms':[]},
]


@pytest.mark.parametrize('spelling',['Asteraimne','Asteramin','Asterramine','Astexamine'])
@pytest.mark.parametrize('question',[
    'Which diseases can {} be used to treat?',
    'What conditions could {} treat?',
    'Which targets may {} have?',
    'What is {} prescribed to treat?',
])
def test_one_edit_drug_names_are_extracted_and_linked(spelling,question):
    candidates,unresolved = Linker(ENTITIES).question_mentions(question.format(spelling))
    assert not unresolved
    assert len(candidates)==1 and candidates[0].uid=='fiction:a'
    assert candidates[0].mention==spelling and not candidates[0].ambiguous


def test_exact_existing_drug_name_is_never_corrected_to_its_neighbor():
    entities = [*ENTITIES,{'uid':'fiction:c','label':'Drug','name':'Asteramide','synonyms':[]}]
    candidates = Linker(entities).link('Asteramide')
    assert len(candidates)==1 and candidates[0].uid=='fiction:c'
    assert candidates[0].method=='exact'


def test_nearby_drugs_stay_ambiguous_instead_of_using_score_margin():
    entities = [*ENTITIES,{'uid':'fiction:c','label':'Drug','name':'Asteramide','synonyms':[]}]
    question = 'Which diseases can Asteramite be used to treat?'
    candidates,unresolved = Linker(entities).question_mentions(question)
    assert not unresolved and {c.uid for c in candidates}=={'fiction:a','fiction:c'}
    assert all(c.ambiguous for c in candidates) and label_choices(candidates) is None
    assert route(question,candidates) is None


def test_several_aliases_of_one_drug_do_not_create_false_ambiguity():
    entities = [dict(ENTITIES[0],synonyms=['Asteramino'])]
    candidates = Linker(entities).link('Asteramin')
    assert len(candidates)==1 and not candidates[0].ambiguous


@pytest.mark.parametrize('mention',['Astrol','ABDC','metaboli','question'])
def test_short_unknown_words_and_gene_symbols_do_not_get_new_corrections(mention):
    entities = [
        {'uid':'fiction:short','label':'Drug','name':'Astorl','synonyms':[]},
        {'uid':'fiction:gene','label':'Gene','name':'ABCD','synonyms':[]},
        {'uid':'fiction:word','label':'Drug','name':'Quesiton','synonyms':[]},
    ]
    assert Linker(entities).link(mention)==[]


def test_exact_only_document_linking_does_not_correct_typos():
    assert Linker(ENTITIES).question_mentions('Asteramin is mentioned.',exact_only=True)==([],[])


def test_unrecognized_modal_anchor_is_retained_for_clarification():
    candidates,unresolved = Linker(ENTITIES).question_mentions(
        'Which diseases can Zorbletrine be used to treat?')
    assert not candidates and unresolved==['zorbletrine']


def test_known_and_misspelled_interaction_anchors_remain_distinct():
    candidates,unresolved = Linker(ENTITIES).question_mentions(
        'Can Asteraimne interact with Brinexamine?')
    assert not unresolved and {c.uid for c in candidates}=={'fiction:a','fiction:b'}
