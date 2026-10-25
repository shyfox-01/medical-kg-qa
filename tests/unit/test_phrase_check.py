"""Partly matched phrases are checked by the model, then confirmed by the user (D106)."""

import pytest

from medkg.qa import confirm
from medkg.qa.linker import Candidate, Linker

ENTITIES = [
    {'uid': 'g:itch', 'label': 'Gene', 'name': 'ITCH', 'synonyms': []},
    {'uid': 'p:pruritus', 'label': 'Phenotype', 'name': 'Pruritus', 'synonyms': ['itchy skin']},
    {'uid': 'd:iron', 'label': 'Drug', 'name': 'Iron', 'synonyms': []},
    {'uid': 'd:zolmi', 'label': 'Drug', 'name': 'Zolmitriptan', 'synonyms': []},
    {'uid': 'x:shingles', 'label': 'Disease', 'name': 'herpes zoster', 'synonyms': ['shingles']},
]


@pytest.mark.parametrize('question,phrase', [
    ('What are the symptoms of jock itch?', 'jock itch'),
    ('What causes iron deficiency?', 'iron deficiency'),
    ('Are iron allergies common?', 'iron allergies'),
])
def test_modifiers_and_head_nouns_make_a_partial_phrase(question, phrase):
    linker = Linker(ENTITIES)
    candidates, _ = linker.question_mentions(question)
    assert [p for p, _ in linker.partial_phrases(question, candidates)] == [phrase]


@pytest.mark.parametrize('question', [
    'Is shingles contagious?', 'Do Zolmitriptan 5mg tablets contain gluten?', 'What is severe shingles?',
    'Which genes does Iron target?', 'How do I taper off Zolmitriptan?',
    'What is the treatment for iron overdose?', 'Who should get the shingles vaccine?',
    "Is the patient's itch a side effect?", 'İzmir: is iron deficiency common?',
])
def test_predicates_doses_severity_and_meta_words_do_not(question):
    linker = Linker(ENTITIES)
    candidates, _ = linker.question_mentions(question)
    assert linker.partial_phrases(question, candidates) == []


def run(question, choice, lookup=None):
    linker = Linker(ENTITIES)
    checked = confirm.review(linker, *linker.question_mentions(question))
    if lookup:
        linker.link = lookup                                # the whole-phrase lookup
    seen = []

    def judge(q, phrase, options):
        seen.append([c.name for c in options])
        picked = choice(options) if callable(choice) else choice
        return picked if picked is None or isinstance(picked, dict) else {picked: 1.0}
    return confirm.check_phrases(linker, question, checked, judge), seen


def test_none_of_them_asks_back_with_the_partial_match():
    checked, _ = run('What causes iron deficiency?', 0)
    assert not checked.kept and [(p, [c.name for c in g]) for p, g in checked.suggestions] == [('iron deficiency', ['Iron'])]


def test_choosing_the_matched_entity_keeps_it():
    checked, _ = run('What are the symptoms of jock itch?', lambda options: 1 + [c.name for c in options].index('ITCH'))
    assert [c.name for c in checked.kept] == ['ITCH'] and not checked.suggestions


def test_a_different_choice_is_offered_first_and_the_match_second():
    pruritus = Candidate('p:pruritus', 'Pruritus', 'Phenotype', 0.9, 'fuzzy', False, 'facial itch', None)
    checked, seen = run('Are rashes and facial itch side effects of Iron?', 2, lambda phrase: [pruritus])
    assert seen == [['ITCH', 'Pruritus']]
    assert [(p, [c.name for c in g]) for p, g in checked.suggestions] == [('facial itch', ['Pruritus', 'ITCH'])]
    assert [c.name for c in checked.kept] == ['Iron']


def test_a_corrected_name_is_not_part_of_a_phrase():
    corrected = Candidate('d:hctz', 'Hydrochlorothiazide', 'Drug', 0.95, 'fuzzy', False, 'hydrochlorothiazid', (1, 2))
    itch = Candidate('g:itch', 'ITCH', 'Gene', 100, 'exact', False, 'itch', (2, 3))
    assert Linker(ENTITIES).partial_phrases('Can hydrochlorothiazid itch happen?', [corrected, itch]) == []


def test_a_phrase_from_a_follow_up_rewrite_is_not_checked():
    # The session rewrite put "Iron" into the question; the user typed only "that deficiency".
    linker = Linker(ENTITIES)
    resolved = 'What about Iron deficiency?'
    checked = confirm.review(linker, *linker.question_mentions(resolved))
    checked = confirm.check_phrases(linker, resolved, checked, lambda *a: 0, typed='What about that deficiency?')
    assert [c.name for c in checked.kept] == ['Iron'] and not checked.suggestions
    assert confirm.written('jock itch', 'Is my Jock-Itch back?') and not confirm.written('s itch', 'this itch')


def test_a_failed_reply_keeps_the_exact_match():
    checked, _ = run('What causes iron deficiency?', None)
    assert [c.name for c in checked.kept] == ['Iron'] and not checked.suggestions


def test_the_phrase_is_returned_as_written_so_a_confirmed_name_can_replace_it():
    linker = Linker(ENTITIES)
    question = 'How does MedlinePlus describe Jock Itch?'
    [(phrase, _)] = linker.partial_phrases(question, linker.question_mentions(question)[0])
    assert phrase == 'Jock Itch'
    confirmed = question.replace(phrase, 'Pruritus')          # what the demo page resubmits
    assert linker.partial_phrases(confirmed, linker.question_mentions(confirmed)[0]) == []


def test_common_words_and_punctuation_end_the_phrase():
    linker = Linker(ENTITIES)
    for question in ('How much Iron is in spinach?', 'I bought Iron at the shop, is it fine?',
                     'He was seen on [DATE]. Itch started later.', 'Is it always itch?'):
        assert linker.partial_phrases(question, linker.question_mentions(question)[0]) == []


def test_the_pipeline_asks_back_when_the_model_rejects_the_match(monkeypatch):
    from tests.unit.test_confirm_names import pipeline
    from tests.unit.test_review_regressions import Model
    model = Model(plan={'choice': 0})
    asked = pipeline(monkeypatch, model).ask('What are the symptoms of an Asterol allergy?')
    assert asked['route'] == 'linking' and asked['refused'] and model.usage['calls'] == 1
    assert asked['suggestions'][0]['mention'] == 'Asterol allergy'
    assert [o['name'] for o in asked['suggestions'][0]['options']] == ['Asterol']
    kept = pipeline(monkeypatch, Model()).ask('What are the symptoms of an Asterol allergy?')
    assert kept['route'] != 'linking'


def test_the_model_judge_returns_none_on_bad_output():
    class Broken:
        def chat_json(self, *args):
            return {'choice': 'many'}
    assert confirm.model_judge(Broken())('q', 'p', []) is None


def test_an_unsure_keep_is_asked_back_with_the_likeliest_other_entry_first():
    pruritus = Candidate('p:pruritus', 'Pruritus', 'Phenotype', 0.9, 'fuzzy', False, 'facial itch', None)
    checked, _ = run('Are rashes and facial itch side effects of Iron?', {1: 0.4, 2: 0.35, 0: 0.25},
                     lambda phrase: [pruritus])
    assert [(p, [c.name for c in g]) for p, g in checked.suggestions] == [('facial itch', ['Pruritus', 'ITCH'])]
    checked, _ = run('Are rashes and facial itch side effects of Iron?', {1: 0.6, 0: 0.4}, lambda phrase: [pruritus])
    assert not checked.suggestions


def test_the_model_judge_reads_probabilities_when_the_endpoint_gives_them():
    class Probabilities:
        def choose(self, messages, options):
            return {0: 0.7, 1: 0.3}
    iron = Candidate('d:iron', 'Iron', 'Drug', 100, 'exact', False, 'iron', (0, 1))
    assert confirm.model_judge(Probabilities())('q', 'p', [iron]) == {0: 0.7, 1: 0.3}
