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
    'Is Asterol not used for Orion syndrome?',
    'Is Asterol no longer used to treat Orion syndrome?',
    'Is Asterol the best treatment for Orion syndrome?',
    'Does Asterol treat Orion syndrome better than diet?',
    'Does anything besides Asterol treat Orion syndrome?',
    'Is Asterol or Brinex used to treat Orion syndrome?',
    'Is Asterol used to treat Orion syndrome? Is it safe?',
])
def test_existential_compound_and_list_questions_do_not(question):
    assert route(question, linked(question)) is None


def test_the_pair_query_filters_one_target_and_states_its_verdict():
    statement, params = templates.query('indications', ['d:a'], target='x:b')
    assert 'b.uid = $target' in statement and params['target'] == 'x:b'
    with pytest.raises(ValueError):
        templates.query('genes', ['x:b'], target='g:c')
    assert templates.pair_verdict('side_effects', 'Asterol', 'Amber spots', True) == (
        'The knowledge graph records Amber spots as a side effect of Asterol.')
    assert templates.pair_verdict('indications', 'asterol', 'Orion syndrome', False) == (
        'Asterol is not recorded as indicated for Orion syndrome in the knowledge graph.')
    assert Step(tool='template', args={'intent': 'indications', 'uids': ['d:a'], 'target': 'x:b'})
    with pytest.raises(ValueError):
        Step(tool='template', args={'intent': 'indications', 'uids': ['d:a'], 'target': 3})


def test_the_pipeline_answers_a_pair_in_code_without_the_model(monkeypatch):
    model = Model()
    result = pipeline(monkeypatch, model).ask('Is Amber spots a side effect of Asterol?')
    assert result['route'] == 'template' and result['intent'] == 'side_effects' and model.usage['calls'] == 0
    assert result['answer'].startswith('The knowledge graph records Amber spots as a side effect of Asterol.')
    assert "b.uid = $target" in result['queries'][0]['cypher']


def test_a_count_question_or_a_count_inside_a_name_is_not_a_yes(monkeypatch):
    from medkg.qa.router import is_count
    spots = linked('Can Asterol cause Amber spots count?')
    assert is_count('Can Asterol cause Amber spots count?') and not is_count('Can Asterol cause Amber spots?', spots)
    model = Model()
    result = pipeline(monkeypatch, model).ask('How many side effects does Asterol have, including Amber spots?')
    assert 'target' not in result['queries'][0].get('params', {}) if result.get('queries') else True


def test_a_personal_pair_question_carries_a_notice(monkeypatch):
    result = pipeline(monkeypatch, Model()).ask('Can Asterol cause Amber spots in my son?')
    assert result['answer'].startswith('Note:') and 'records Amber spots as a side effect of Asterol' in result['answer']


def test_the_verdict_uses_the_name_as_written():
    from medkg.qa.linker import Candidate
    from medkg.qa.pipeline import Pipeline
    stub = Pipeline.__new__(Pipeline)
    stub.linker = Linker(copy.deepcopy(ENTITIES))
    written = Candidate('fiction:drug-a', 'Asterol', 'Drug', 100, 'exact', False, 'Astrolex', (0, 1))
    assert stub._written({'fiction:drug-a': written}, 'fiction:drug-a') == 'Astrolex (Asterol)'
    assert stub._written({}, 'fiction:drug-a') == 'Asterol'
