"""Exact-only alias boundaries, using small catalogs and fixed vector fixtures."""

import numpy as np
import pytest

from medkg.qa.linker import Linker
from medkg.qa.verify import entities_in_text


@pytest.fixture
def entities():
    return [
        {'uid': 'fixture:niraparib', 'name': 'Niraparib', 'label': 'Drug',
         'synonyms': [], 'exact_synonyms': ['Zejula', 'Aurorabrand', 'Amber Orchard']},
        {'uid': 'fixture:lidocaine', 'name': 'Lidocaine', 'label': 'Drug',
         'synonyms': [], 'exact_synonyms': ['Medicone']},
    ]


@pytest.mark.parametrize('label', [None, 'Drug'])
def test_exact_only_brand_links_directly_with_optional_label(entities, label):
    candidates = Linker(entities).link('ZEJULA', label)
    assert len(candidates) == 1
    assert candidates[0].uid == 'fixture:niraparib'
    assert candidates[0].method == 'exact'
    assert candidates[0].score == 100
    assert not candidates[0].ambiguous
    assert Linker(entities).link('Zejula', 'Disease') == []


def test_exact_only_brand_is_an_explicit_question_mention(entities):
    candidates, unresolved = Linker(entities).question_mentions('What is Zejula used for?')
    assert not unresolved
    assert len(candidates) == 1
    assert candidates[0].uid == 'fixture:niraparib'
    assert candidates[0].method == 'exact'
    assert candidates[0].mention == 'Zejula'
    assert candidates[0].span == (2, 3)


def test_common_word_does_not_correct_to_an_exact_only_brand(entities):
    linker = Linker(entities)
    assert linker.link('medicine', 'Drug') == []
    candidates, _ = linker.question_mentions('Is medicine safe during pregnancy?')
    assert candidates == []
    assert linker.link('Medicone', 'Drug')[0].uid == 'fixture:lidocaine'


@pytest.mark.parametrize('label', [None, 'Drug'])
@pytest.mark.parametrize('mention', ['Aurorabrnad', 'Aurorabran', 'Orchard Amber'])
def test_exact_only_alias_is_not_a_single_edit_or_token_sort_target(entities, mention, label):
    linker = Linker(entities)
    assert linker.link(mention, label) == []
    candidates, unresolved = linker.question_mentions(f'What is {mention} used for?')
    assert candidates == []
    assert unresolved == [mention.casefold()]


@pytest.mark.parametrize('mention', ['Asteraimne', 'Orchard Amber'])
@pytest.mark.parametrize('label', [None, 'Drug'])
def test_ordinary_synonyms_keep_single_edit_and_token_sort_matching(entities, mention, label):
    entities[0]['synonyms'] = ['Asteramine', 'Amber Orchard']
    candidates = Linker(entities).link(mention, label)
    assert len(candidates) == 1
    assert candidates[0].uid == 'fixture:niraparib'
    assert candidates[0].method == 'fuzzy'
    assert not candidates[0].ambiguous


def test_fuzzy_eligibility_is_specific_to_the_alias_owner(entities):
    entities[1]['synonyms'] = ['Aurorabrand']
    linker = Linker(entities)
    exact = linker.link('Aurorabrand', 'Drug')
    assert {candidate.uid for candidate in exact} == {'fixture:niraparib', 'fixture:lidocaine'}
    assert all(candidate.ambiguous for candidate in exact)
    fuzzy = linker.link('Aurorabrnad', 'Drug')
    assert [candidate.uid for candidate in fuzzy] == ['fixture:lidocaine']
    assert fuzzy[0].method == 'fuzzy'


def test_exact_document_scans_include_exact_only_aliases(entities):
    linker = Linker(entities)
    text = 'The document mentions Zejula and Medicone.'
    candidates, unresolved = linker.question_mentions(text, exact_only=True)
    expected = {'fixture:niraparib', 'fixture:lidocaine'}
    assert {candidate.uid for candidate in candidates} == expected
    assert all(candidate.method == 'exact' for candidate in candidates)
    assert not unresolved
    assert entities_in_text(text, linker) == expected
    assert entities_in_text('The document mentions Aurorabrnad.', linker) == set()


def test_exact_document_scan_preserves_literal_separator_aliases(entities):
    entities[0]['exact_synonyms'] = ['Amber, Orchard']
    entities[1]['exact_synonyms'] = ['Crimson Meadow']
    linker = Linker(entities)
    assert entities_in_text('Amber, Orchard is mentioned.', linker) == {'fixture:niraparib'}
    assert entities_in_text('Crimson, Meadow is mentioned.', linker) == set()


class FixedEncoder:
    def encode(self, texts):
        return np.array([[1.0, 0.0] for _ in texts])


def test_stale_exact_only_vector_rows_do_not_outrank_allowed_rows(entities):
    entities[1]['synonyms'] = ['Aurorabrand']
    linker = Linker(entities, FixedEncoder(), np.array([[1., 0.], [.95, 0.], [.90, 0.]]), [
        {'uid': 'fixture:niraparib', 'text': 'Aurorabrand'},
        {'uid': 'fixture:lidocaine', 'text': 'Aurorabrand'},
        {'uid': 'fixture:niraparib', 'text': 'Niraparib'},
    ])
    candidates = linker.link('Uncatalogued concept', 'Drug')
    assert [candidate.uid for candidate in candidates] == ['fixture:lidocaine', 'fixture:niraparib']
    assert [candidate.score for candidate in candidates] == pytest.approx([.95, .90])
    assert all(candidate.method == 'vector' for candidate in candidates)
    assert linker.link('Uncatalogued concept', 'Disease') == []


def test_only_stale_exact_only_vector_rows_produce_no_candidate(entities):
    linker = Linker(entities, FixedEncoder(), np.array([[1., 0.]]), [
        {'uid': 'fixture:niraparib', 'text': 'Zejula'},
    ])
    assert linker.link('Uncatalogued concept') == []
    assert linker.link('Zejula')[0].method == 'exact'


def test_allowed_grouped_canonical_vector_rows_keep_existing_behavior():
    entities = [
        {'uid': 'fixture:disease', 'name': 'Orion fever', 'label': 'Disease', 'synonyms': []},
        {'uid': 'MONDO_grouped:fixture', 'name': 'Orion fever,', 'label': 'Disease',
         'synonyms': ['Orion fever subtype']},
    ]
    linker = Linker(entities, FixedEncoder(), np.array([[1., 0.]]), [
        {'uid': 'MONDO_grouped:fixture', 'text': 'Orion fever,'},
    ])
    assert [candidate.uid for candidate in linker.link('Orion fever')] == ['fixture:disease']
    candidates = linker.link('Uncatalogued concept', 'Disease')
    assert [candidate.uid for candidate in candidates] == ['MONDO_grouped:fixture']
    assert candidates[0].method == 'vector'
