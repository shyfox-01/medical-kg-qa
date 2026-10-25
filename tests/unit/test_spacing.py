"""Names typed with a missing or extra space are matched and used with a note (D107)."""

import pytest

from medkg.qa import confirm
from medkg.qa.linker import Linker

ENTITIES = [
    {'uid': 'd:metformin', 'label': 'Drug', 'name': 'Metformin', 'synonyms': []},
    {'uid': 'd:abrilada', 'label': 'Drug', 'name': 'Adalimumab', 'synonyms': [], 'exact_synonyms': ['Abrilada']},
    {'uid': 'x:hf', 'label': 'Disease', 'name': 'heart failure', 'synonyms': []},
    {'uid': 'x:di', 'label': 'Disease', 'name': 'diabetes insipidus', 'synonyms': []},
    {'uid': 'x:bd', 'label': 'Disease', 'name': 'bone dysplasia', 'synonyms': []},
    {'uid': 'x:bdh', 'label': 'Disease', 'name': 'bone dysplasia, lethal Holmgren type', 'synonyms': []},
    {'uid': 'x:root', 'label': 'Disease', 'name': 'disease', 'synonyms': []},
    {'uid': 'x:mela', 'label': 'Disease', 'name': 'Mela syndrome', 'synonyms': ['mela']},
    {'uid': 'x:noma', 'label': 'Disease', 'name': 'noma', 'synonyms': []},
    {'uid': 'x:melanoma', 'label': 'Disease', 'name': 'melanoma', 'synonyms': []},
    {'uid': 'd:ramipril', 'label': 'Drug', 'name': 'Ramipril', 'synonyms': []},
    {'uid': 'd:ramiprilat', 'label': 'Drug', 'name': 'Ramiprilat', 'synonyms': []},
    {'uid': 'p:edema', 'label': 'Phenotype', 'name': 'Edema', 'synonyms': []},
    {'uid': 'x:lipedema', 'label': 'Disease', 'name': 'Lipedema', 'synonyms': []},
    {'uid': 'x:lip', 'label': 'Phenotype', 'name': 'Lip pit', 'synonyms': []},
    {'uid': 'x:dm', 'label': 'Disease', 'name': 'diabetes mellitus', 'synonyms': ['diabetes']},
    {'uid': 'x:t2', 'label': 'Disease', 'name': 'type 2 diabetes', 'synonyms': []},
]


def review(question):
    linker = Linker(ENTITIES)
    return confirm.review(linker, *linker.question_mentions(question))


@pytest.mark.parametrize('question,mention,uid', [
    ('What is metf ormin used for?', 'metf ormin', 'd:metformin'),
    ('Is type2 diabetes hereditary?', 'type2 diabetes', 'x:t2'),
    ('What treats heartfailure?', 'heartfailure', 'x:hf'),
    ('What causes diabetesinsipidus?', 'diabetesinsipidus', 'x:di'),
    ('What are the side effects of metformintablets?', 'metformintablets', 'd:metformin'),
    ('What is bonedysplasia, lethal Holmgren type?', 'bonedysplasia lethal Holmgren type', 'x:bdh'),
])
def test_a_space_fix_is_used_with_a_note(question, mention, uid):
    checked = review(question)
    assert [c.uid for c in checked.kept] == [uid] and not checked.suggestions
    assert [m for m, _ in checked.corrections] == [mention]      # word tokens as typed
    assert checked.kept[0].method == 'spacing'


@pytest.mark.parametrize('question', [
    'Which disease entities is noma a subtype of?',      # a skipped generic word stays skipped
    'What is mela noma?',                               # two names are not joined into a third
    'What does Abri lada treat?',                       # RxNorm-only names are not correction targets
    'Is it heart. Failure is rare?',                    # a full stop ends the window
    'Should I take ramipril at night?',                  # a common word never joins a name
    'Why do I get lip edema after taking ramipril?',     # two known words are written on purpose
])
def test_no_space_fix(question):
    linker = Linker(ENTITIES)
    candidates, _ = linker.question_mentions(question)
    assert not [c for c in candidates if c.method == 'spacing']


def test_an_entity_named_elsewhere_keeps_its_mention():
    linker = Linker(ENTITIES)
    candidates, _ = linker.question_mentions('My mom has diabetes and I have type2 diabetes, is it hereditary?')
    assert {c.uid for c in candidates} == {'x:dm', 'x:t2'}
