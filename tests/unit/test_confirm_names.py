"""Confirm corrected names before answering (D105)."""

import copy

from eval.score import CLARIFY
from medkg.config import Settings
from medkg.qa import confirm
from medkg.qa.linker import Candidate, Linker
from medkg.qa.pipeline import Pipeline
from tests.unit.test_review_regressions import ENTITIES, Model, Store, span, trace

NAMES = ENTITIES + [
    {'uid': 'fiction:zeltaramin', 'label': 'Drug', 'name': 'Zeltaramin', 'synonyms': []},
    {'uid': 'fiction:corvalintex', 'label': 'Drug', 'name': 'Corvalintex', 'synonyms': []},
    {'uid': 'fiction:corvalintax', 'label': 'Drug', 'name': 'Corvalintax', 'synonyms': []},
]


def pipeline(monkeypatch, model):
    monkeypatch.setattr('medkg.qa.pipeline.request_trace', trace)
    monkeypatch.setattr('medkg.qa.pipeline.span', span)
    return Pipeline(Settings(phase=3, cache=False), store=Store(), llm=model, entities=copy.deepcopy(NAMES))


def review(question):
    linker = Linker(NAMES)
    return confirm.review(linker, *linker.question_mentions(question))


def test_a_one_edit_long_name_without_lookalikes_is_used_with_a_note():
    checked = review('What is Zeltaramyn used for?')
    assert [c.uid for c in checked.kept] == ['fiction:zeltaramin'] and not checked.suggestions
    assert confirm.correction_notice(checked.corrections) == 'Note: read "Zeltaramyn" as Zeltaramin.'


def test_a_correction_with_a_lookalike_nearby_is_asked_back():
    checked = review('What is Corvalintix used for?')
    assert checked.suggestions and not checked.kept
    assert 'Did you mean' in confirm.clarification(checked.suggestions)


def test_an_unresolved_misspelling_gets_the_nearest_spelling():
    checked = review('What is Zletaramni used for?')
    assert [[o['name'] for o in g['options']] for g in confirm.describe(checked.suggestions)] == [['Zeltaramin']]


def test_ordinary_words_get_no_suggestion():
    assert not review('What does testing show about Asterol?').suggestions
    assert confirm.suggestion_edits('testing') == 1 and confirm.suggestion_edits('pension') == 1
    assert confirm.suggestion_edits('legs') == 0


def candidate(uid, name, method, mention, span=(0, 1)):
    return Candidate(uid, name, 'Disease', 0.9, method, False, mention, span)


def test_vector_matches_are_dropped_next_to_anchors_and_need_a_shared_stem_alone():
    linker = Linker(NAMES)
    exact = candidate('fiction:disease', 'Orion syndrome', 'exact', 'Orion syndrome', (3, 5))
    vector = candidate('x:small-hand', 'Small hand', 'vector', 'hands', (0, 1))
    checked = confirm.review(linker, [exact, vector], [])
    assert checked.kept == [exact] and 'hand' in checked.unresolved and not checked.suggestions
    alone = confirm.review(linker, [candidate('x:asthma', 'asthma', 'vector', 'asthmatics')], [])
    assert [c.name for _, group in alone.suggestions for c in group] == ['asthma']
    unrelated = confirm.review(linker, [candidate('x:med', 'multiple epiphyseal dysplasia', 'vector', 'MEDICINE')], [])
    assert not unrelated.suggestions and unrelated.unresolved == ['medicine']


def test_the_pipeline_asks_before_answering_and_notes_confident_corrections(monkeypatch):
    model = Model()
    asked = pipeline(monkeypatch, model).ask('What are the side effects of Corvalintix?')
    # One call orders the two spellings (D118); this fixture's reply is invalid, so the order stays.
    assert asked['route'] == 'linking' and asked['refused'] and model.usage['calls'] == 1
    assert asked['suggestions'][0]['mention'] == 'Corvalintix'
    assert {o['name'] for o in asked['suggestions'][0]['options']} <= {'Corvalintex', 'Corvalintax'}
    assert CLARIFY.search(asked['answer'])
    noted = pipeline(monkeypatch, Model()).ask('What is Zeltaramyn used for?')
    assert noted['answer'].startswith('Note: read "Zeltaramyn" as Zeltaramin.')
    assert noted['corrections'][0]['options'][0]['uid'] == 'fiction:zeltaramin'


def test_the_demo_page_renders_the_confirmation():
    from pathlib import Path
    page = (Path(__file__).resolve().parents[2]/'src/medkg/api/static/index.html').read_text(encoding='utf8')
    assert 'Did you mean' in page and 'None of these' in page and 'suggestions' in page
