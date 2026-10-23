"""The reviewed MeSH class aliases must not identify Pentastarch (D101)."""

import pytest

from eval.score import Vocabulary
from medkg.qa.linker import Linker
from medkg_data.alias_policy import allowed_names, exact_names

REJECTED = [
    '2-Hydroxyethyl Starches', 'Elohes', 'HAES-steril', 'Hemohes', 'Hespan',
    'Hetastarch', 'Hydroxyethyl Starch (130 KD-0.4 Substitution)',
    'Hydroxyethyl Starch 130-0.4', 'Hydroxyethyl Starch Derivatives',
    'Hydroxyethylated Starches', 'Plasmasteril',
]
RETAINED = ['Pentaspan', 'Pentafraction']
UID = 'DrugBank:DB09111'


@pytest.mark.parametrize('field', ['synonyms', 'exact_synonyms'])
@pytest.mark.parametrize('alias', REJECTED)
def test_reviewed_class_aliases_never_link_or_score_as_pentastarch(field, alias):
    entity = {'uid': UID, 'label': 'Drug', 'name': 'Pentastarch',
              field: [*REJECTED, *RETAINED]}
    linker = Linker([entity])
    question = f'What is {alias} used for?'
    assert linker.link(alias) == []
    assert linker.question_mentions(question)[0] == []
    assert Vocabulary([entity]).extract(question) == set()
    assert exact_names(entity) == ['Pentastarch', *RETAINED]
    assert allowed_names(entity) == (
        ['Pentastarch', *RETAINED] if field == 'synonyms' else ['Pentastarch'])
    assert entity[field] == [*REJECTED, *RETAINED]


@pytest.mark.parametrize('alias', ['Pentastarch', *RETAINED])
def test_pentastarch_product_names_remain_linkable(alias):
    entity = {'uid': UID, 'label': 'Drug', 'name': 'Pentastarch',
              'synonyms': [*REJECTED, *RETAINED]}
    linker = Linker([entity])
    question = f'What is {alias} used for?'
    assert [candidate.uid for candidate in linker.link(alias)] == [UID]
    assert [candidate.uid for candidate in linker.question_mentions(question)[0]] == [UID]
    assert Vocabulary([entity]).extract(question) == {UID}
