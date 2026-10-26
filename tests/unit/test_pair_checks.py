"""Yes/no questions about one drug and one disease or phenotype check that pair (D112)."""

import copy

import pytest

from medkg.qa.linker import Linker
from medkg.qa.planner import Step
from medkg.qa.router import route
from medkg.retrieval import templates
from tests.unit.test_confirm_names import pipeline
from tests.unit.test_review_regressions import ENTITIES, Model


def linked(question):
    candidates, _ = Linker(copy.deepcopy(ENTITIES)).question_mentions(question)
    return candidates


@pytest.mark.parametrize('question,intent', [
    ('Is Asterol used to treat Orion syndrome?', 'indications'),
    ('Does Asterol treat Orion syndrome?', 'indications'),
    ('Can Asterol be used for Orion syndrome?', 'indications'),
    ('Is Asterol contraindicated in Orion syndrome?', 'contraindications'),
    ('Is Orion syndrome a contraindication for Asterol?', 'contraindications'),
    ('Can Asterol cause Amber spots?', 'side_effects'),
    ('Is Amber spots a side effect of Asterol?', 'side_effects'),
])
def test_a_yes_no_question_about_a_drug_and_a_condition_routes_to_its_pair(question, intent):
    assert route(question, linked(question)) == intent


@pytest.mark.parametrize('question', [
    'Are there Orion syndrome treatments other than Asterol?',
    'Is Asterol a steroid and is it contraindicated in Orion syndrome?',
    'Which drugs besides Asterol treat Orion syndrome?',
])
def test_existential_compound_and_list_questions_do_not(question):
    assert route(question, linked(question)) is None


def test_the_pair_query_filters_one_target_and_states_its_verdict():
    statement, params = templates.query('indications', ['d:a'], target='x:b')
    assert 'b.uid = $target' in statement and params['target'] == 'x:b'
    with pytest.raises(ValueError):
        templates.query('genes', ['x:b'], target='g:c')
    assert templates.pair_verdict('side_effects', 'Asterol', 'Amber spots', True) == (
        'Yes. The knowledge graph records Amber spots as a side effect of Asterol.')
    assert templates.pair_verdict('indications', 'asterol', 'Orion syndrome', False) == (
        'Asterol is not recorded as indicated for Orion syndrome in the knowledge graph.')
    assert Step(tool='template', args={'intent': 'indications', 'uids': ['d:a'], 'target': 'x:b'})
    with pytest.raises(ValueError):
        Step(tool='template', args={'intent': 'indications', 'uids': ['d:a'], 'target': 3})


def test_the_pipeline_answers_a_pair_in_code_without_the_model(monkeypatch):
    model = Model()
    result = pipeline(monkeypatch, model).ask('Is Amber spots a side effect of Asterol?')
    assert result['route'] == 'template' and result['intent'] == 'side_effects' and model.usage['calls'] == 0
    assert result['answer'].startswith('Yes. The knowledge graph records Amber spots as a side effect of Asterol.')
    assert "b.uid = $target" in result['queries'][0]['cypher']
