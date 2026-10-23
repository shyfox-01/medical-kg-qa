"""Reversible pair-level policy, using fictional fixtures and source-reviewed names."""

from types import SimpleNamespace

import numpy as np
import pytest

from medkg.config import Settings
from medkg.qa.linker import Linker
from medkg.qa.pipeline import Pipeline
from medkg_data.alias_policy import EXCLUDED_ALIASES, allowed_names, is_excluded
from medkg_data.synonyms import merge_synonyms
from scripts.build_vector_corpus import prioritized_synonyms


@pytest.fixture
def policy(monkeypatch):
    exclusions = {'fiction:drug': frozenset({'asterol a', 'asterol', 'family brand'})}
    monkeypatch.setattr('medkg_data.alias_policy.EXCLUDED_ALIASES', exclusions)
    monkeypatch.setattr('medkg.qa.linker.EXCLUDED_ALIASES', exclusions)
    return [
        {'uid': 'fiction:drug', 'name': 'Asterol B', 'label': 'Drug',
         'synonyms': ['Asterol A', 'Asterol', 'Family brand', 'Star brand', 'Uncertain brand']},
        {'uid': 'fiction:other', 'name': 'Other substance', 'label': 'Drug', 'synonyms': []},
    ]


def test_policy_covers_29_pairs_and_preserves_canonical_names():
    assert sum(map(len, EXCLUDED_ALIASES.values())) == 29
    assert is_excluded('DrugBank:DB00105', 'Interferon alfa-2a')
    assert not is_excluded('DrugBank:DB00105', 'Interferon alfa-2b')
    assert not is_excluded('DrugBank:DB00027', 'Linear Gramicidin')
    assert not is_excluded('DrugBank:DB00394', 'Qvar')  # Unresolved, not rejected.


def test_exact_fuzzy_and_stale_vector_rows_cannot_reintroduce_pair(policy):
    class Encoder:
        def encode(self, texts):
            return np.array([[1.0, 0.0] for _ in texts])

    linker = Linker(policy, Encoder(), np.array([[1., 0.], [.95, 0.], [.9, 0.]]), [
        {'uid': 'fiction:drug', 'text': 'Asterol A'},
        {'uid': 'fiction:drug', 'text': 'Asterol B'},
        {'uid': 'fiction:other', 'text': 'Other substance'},
    ])
    # A versus B would exceed the old fuzzy threshold, even without the stale alias.
    assert 'fiction:drug' not in {c.uid for c in linker.link('Asterol A')}
    linker.vector_aliases = [linker.vector_aliases[0]]
    linker.vectors = np.array([[1., 0.]])
    assert not linker.link('Unrelated unresolved token')
    assert linker.link('Asterol B')[0].uid == 'fiction:drug'
    assert linker.link('Star brand')[0].uid == 'fiction:drug'
    assert linker.link('Uncertain brand')[0].uid == 'fiction:drug'


def test_whole_phrase_is_reserved_but_longer_canonical_and_other_owner_survive(policy):
    linker = Linker(policy)
    found, unresolved = linker.question_mentions('What is Asterol A indicated for?')
    assert not found and linker.quarantined_mentions(unresolved) == ['asterol a']
    found, unresolved = linker.question_mentions('What is Asterol B indicated for?')
    assert [c.uid for c in found] == ['fiction:drug']
    assert not linker.quarantined_mentions(unresolved)
    policy[1]['synonyms'] = ['Asterol A']
    linker = Linker(policy)
    found, unresolved = linker.question_mentions('What is Asterol A indicated for?')
    assert [c.uid for c in found] == ['fiction:other']
    assert not linker.quarantined_mentions(unresolved)


@pytest.mark.parametrize('mode', ['hybrid', 'vector'])
def test_quarantined_unresolved_name_stops_before_planning_and_retrieval(policy, mode):
    class Model:
        usage = {'calls': 0, 'prompt_tokens': 0, 'completion_tokens': 0}

        def complete(self, *args, **kwargs):
            raise AssertionError('Quarantined identity must not reach the model')

    store = SimpleNamespace(executed_statements=[])
    pipeline = Pipeline(Settings(cache=False), store=store, llm=Model(), entities=policy, mode=mode)
    result = pipeline.ask('What is Asterol A indicated for?')
    assert result['refused'] and result['route'] == 'linking'
    assert result['quarantined_mentions'] == ['asterol a']
    assert result['usage']['calls'] == 0 and result['contexts'] == []


def test_future_embedding_corpus_and_enrichment_exclude_only_reviewed_pairs(policy):
    entity = policy[0]
    assert allowed_names(entity) == ['Asterol B', 'Star brand', 'Uncertain brand']
    assert prioritized_synonyms(entity, ['Family brand', 'Star brand']) == [
        'Star brand', 'Uncertain brand']
    additions, skipped = merge_synonyms(policy, [
        ('fiction:drug', 'Asterol A', 'mesh:fiction'),
        ('fiction:drug', 'New safe brand', 'mesh:fiction'),
    ])
    assert skipped['review_quarantine'] == 1
    assert len(additions) == 1 and additions[0]['alias'] == 'New safe brand'
    assert 'Asterol A' in entity['synonyms']  # Original catalog is not mutated.
