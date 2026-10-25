"""A contraction or possessive ending never starts a name (D109)."""

import pytest

from medkg.qa.linker import Linker

ENTITIES = [
    {'uid': 'd:warfarin', 'label': 'Drug', 'name': 'Warfarin', 'synonyms': []},
    {'uid': 'd:s-warfarin', 'label': 'Drug', 'name': '(S)-Warfarin', 'synonyms': []},
    {'uid': 'x:crohn', 'label': 'Disease', 'name': "Crohn's disease", 'synonyms': []},
    {'uid': 'x:t-cell', 'label': 'Disease', 'name': 'T-cell lymphoma', 'synonyms': []},
]


@pytest.mark.parametrize('question', [
    "What's warfarin for?", "What’s warfarin for?", "My mother's warfarin dose is high.",
])
def test_an_s_after_an_apostrophe_is_not_the_start_of_a_name(question):
    candidates, _ = Linker(ENTITIES).question_mentions(question)
    assert [c.uid for c in candidates] == ['d:warfarin']


def test_names_that_contain_a_possessive_and_real_s_names_still_match():
    linker = Linker(ENTITIES)
    assert [c.uid for c in linker.question_mentions("What causes Crohn's disease?")[0]] == ['x:crohn']
    assert [c.uid for c in linker.question_mentions('Is (S)-warfarin active?')[0]] == ['d:s-warfarin']
    assert [c.uid for c in linker.question_mentions("Don't T-cell lymphoma patients relapse?")[0]] == ['x:t-cell']
    assert [c.uid for c in linker.question_mentions("It isn't cell lymphoma")[0]] == []    # "isn't" + "cell"
