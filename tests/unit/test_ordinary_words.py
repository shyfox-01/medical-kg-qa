"""A lower-case word that matched only an acronym or gene symbol is checked by the model (D116)."""

import pytest

from medkg.qa import confirm
from medkg.qa.linker import Candidate, Linker

ENTITIES = [
    {'uid': 'x:hards', 'label': 'Disease', 'name': 'hantavirus fiction syndrome', 'synonyms': ['HARDS']},
    {'uid': 'g:itch', 'label': 'Gene', 'name': 'ITCH', 'synonyms': []},
    {'uid': 'g:cbs', 'label': 'Gene', 'name': 'CBS', 'synonyms': []},
    {'uid': 'p:pruritus', 'label': 'Phenotype', 'name': 'Pruritus', 'synonyms': ['Itching']},
    {'uid': 'x:copd', 'label': 'Disease', 'name': 'chronic obstructive fiction disease', 'synonyms': ['COLD', 'cold']},
    {'uid': 'd:asterol', 'label': 'Drug', 'name': 'Asterol', 'synonyms': []},
    {'uid': 'd:jakafi', 'label': 'Drug', 'name': 'Ruxolifiction', 'synonyms': ['JAKAFI']},
    {'uid': 'g:ifna9', 'label': 'Gene', 'name': 'IFNA9', 'synonyms': []},
]
PRURITUS = Candidate('p:pruritus', 'Pruritus', 'Phenotype', 0.94, 'vector', False)


def linker():
    found = Linker(ENTITIES)
    found.neighbors = lambda word, exclude: [PRURITUS] if word.casefold() == 'itch' else []
    return found


def mentions(question):
    lk = linker()
    return lk, {c.mention: c for c in lk.question_mentions(question)[0]}


def run(question, choice):
    lk = linker()
    checked = confirm.review(lk, *lk.question_mentions(question))
    seen = []

    def judge(q, word, options):
        seen.append((word, [c.name for c in options]))
        return choice if choice is None or isinstance(choice, dict) else {choice: 1.0}
    return confirm.check_words(lk, question, checked, judge, typed=question), seen


def test_only_a_lower_case_word_matching_capitalised_names_is_checked():
    lk, found = mentions('Is Asterol hard on the body, and is ITCH or cbs involved?')
    assert lk.capitals_only(found['hard']) and lk.capitals_only(found['cbs'])
    assert not lk.capitals_only(found['ITCH'])            # typed as the symbol
    assert not lk.capitals_only(found['Asterol'])         # a name, not an acronym
    lk, found = mentions('Which drugs treat chronic obstructive fiction disease?')
    assert not any(lk.capitals_only(c) for c in found.values())
    # Brand names are listed in capitals, and a symbol with digits is no ordinary word.
    lk, found = mentions('What is Jakafi used for, and is ifna9 its target?')
    assert set(found) == {'Jakafi', 'ifna9'} and not any(lk.capitals_only(c) for c in found.values())


def test_an_ordinary_word_is_dropped_without_a_question():
    checked, seen = run('Is Asterol hard on the body?', 0)
    assert seen == [('hard', ['hantavirus fiction syndrome'])]
    assert [c.name for c in checked.kept] == ['Asterol'] and checked.ignored == ['hard']
    assert not checked.suggestions and not checked.unresolved


def test_a_word_meaning_another_entry_is_asked_back_with_it():
    checked, seen = run('Why does my skin itch after Asterol?', 2)
    assert seen == [('itch', ['ITCH', 'Pruritus'])]
    assert [(w, [c.name for c in g]) for w, g in checked.suggestions] == [('itch', ['Pruritus'])]
    assert [c.name for c in checked.kept] == ['Asterol']


def test_a_symbol_the_model_confirms_and_a_failed_reply_keep_the_match():
    checked, _ = run('Which diseases is cbs associated with?', 1)
    assert [c.name for c in checked.kept] == ['CBS'] and not checked.ignored
    checked, _ = run('Is Asterol hard on the body?', None)
    assert {c.name for c in checked.kept} == {'Asterol', 'hantavirus fiction syndrome'}


def test_the_pipeline_drops_the_ordinary_word(monkeypatch):
    from tests.unit.test_confirm_names import pipeline
    from tests.unit.test_review_regressions import Model
    p = pipeline(monkeypatch, Model(plan={'choice': 0}))   # the judge's JSON reply: none of these
    p.linker = Linker(ENTITIES)
    asked = p.ask('Is Asterol hard on the body?')
    assert asked['ignored_words'] == ['hard']
    assert [c['name'] for c in asked['candidates']] == ['Asterol']


@pytest.mark.parametrize('scores,decision,offered', [
    ({1: 0.6, 0: 0.4}, 'keep', []),
    ({2: 0.7, 1: 0.2, 0: 0.1}, 'ask', ['Pruritus', 'ITCH']),
    ({0: 0.7, 1: 0.3}, 'ask', ['ITCH']),
    ({0: 0.95, 1: 0.05}, 'none', []),
])
def test_the_decision_rule(scores, decision, offered):
    itch = Candidate('g:itch', 'ITCH', 'Gene', 100, 'exact', False)
    result = confirm.decide(scores, [itch, PRURITUS], [itch])
    assert result[0] == decision and [c.name for c in result[1]] == offered
