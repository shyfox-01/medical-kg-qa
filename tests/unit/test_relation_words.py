"""Relation nouns are not names, "prescribed for" asks indications, and interactions among
several drugs are stated pair by pair (D113)."""

import copy

from medkg.qa.linker import Linker
from medkg.qa.router import route
from medkg.retrieval import templates
from tests.unit.test_confirm_names import NAMES, pipeline
from tests.unit.test_review_regressions import Model


def mentions(question):
    return Linker(copy.deepcopy(NAMES)).question_mentions(question)


def test_plural_relation_nouns_are_not_unresolved_names():
    for question in ('What are the contraindications for Asterol?', 'Are there any drug interactions between Asterol and Brinex?',
                     'What are the indications of Asterol?'):
        candidates, unresolved = mentions(question)
        assert not unresolved, (question, unresolved)
        assert route(question, candidates) in ('contraindications', 'interactions', 'indications')


def test_prescribed_for_asks_indications_but_how_prescribed_does_not():
    assert route('What is Asterol prescribed for?', mentions('What is Asterol prescribed for?')[0]) == 'indications'
    assert route('How is Asterol prescribed?', mentions('How is Asterol prescribed?')[0]) is None


def test_interactions_among_three_drugs_check_every_pair():
    statement, params = templates.query('interactions', ['d:a', 'd:b', 'd:c'])
    assert 'a.uid IN $uids AND b.uid IN $uids AND a.uid < b.uid' in statement and params == {'uids': ['d:a', 'd:b', 'd:c']}
    names = {'d:a': 'A', 'd:b': 'B', 'd:c': 'C'}
    rows = [{'anchor_uid': 'd:a', 'uid': 'd:b'}, {'anchor_uid': 'd:a', 'uid': 'd:c'}]
    assert templates.interaction_verdict(names, ['d:a', 'd:b', 'd:c'], rows) == (
        'The knowledge graph records interactions between A and B; A and C. It records no interaction between B and C.')
    assert templates.interaction_verdict(names, ['d:a', 'd:b', 'd:c'], []).startswith(
        'The knowledge graph records no interaction between A and B; A and C; B and C.')


def test_the_pipeline_states_a_three_drug_answer_in_code(monkeypatch):
    model = Model()
    result = pipeline(monkeypatch, model).ask('Do Asterol, Brinex and Zeltaramin interact?')
    assert result['route'] == 'template' and result['intent'] == 'interactions' and model.usage['calls'] == 0
    assert result['answer'].startswith('The knowledge graph records')
