"""Graph serialization keeps full-text search and fuzzy alias matching separate."""

from copy import deepcopy

import pytest

from medkg.graph.store import GraphStore, entity_alias_properties
from medkg.qa.linker import Linker


class MemoryStore(GraphStore):
    def __init__(self, rows: list[dict] | None = None):
        self.rows = rows or []
        self.writes = []

    def read(self, statement, params=None, timeout=None):
        return self.rows

    def write(self, statement, params=None):
        self.writes.append((statement, params))
        return []


def entity(**aliases):
    return {'uid': 'fiction:drug', 'label': 'Drug', 'name': 'Fictional Ingredient', **aliases}


def test_graph_alias_properties_keep_raw_union_without_mutating_catalog():
    original = entity(synonyms=['Legacy brand', 'Legacy brand'],
                      exact_synonyms=['Zejula', 'Medicone', 'Zejula'])
    before = deepcopy(original)
    assert entity_alias_properties(original) == {
        'synonyms': ['Legacy brand', 'Zejula', 'Medicone'],
        'exact_synonyms': ['Zejula', 'Medicone'],
    }
    assert original == before


def test_graph_round_trip_keeps_exact_aliases_out_of_fuzzy_linking():
    original = entity(synonyms=['Legacy brand'], exact_synonyms=['Medicone', 'Zejula'])
    stored = {**original, **entity_alias_properties(original)}
    before = deepcopy(stored)
    restored = MemoryStore([stored]).entities()[0]
    assert restored['synonyms'] == ['Legacy brand']
    assert restored['exact_synonyms'] == ['Medicone', 'Zejula']
    linker = Linker([restored])
    assert linker.link('Zejula', 'Drug')[0].uid == original['uid']
    assert linker.link('Medicone', 'Drug')[0].uid == original['uid']
    assert linker.link('medicine', 'Drug') == []
    assert linker.link('Medicome', 'Drug') == []
    assert stored == before


@pytest.mark.parametrize('metadata', [{}, {'exact_synonyms': None}])
def test_graph_reader_preserves_legacy_aliases_without_exact_metadata(metadata):
    original = entity(synonyms=['Legacy brand'], **metadata)
    restored = MemoryStore([original]).entities()[0]
    assert restored['synonyms'] == ['Legacy brand']
    assert restored['exact_synonyms'] == []


def test_graph_reader_accepts_null_legacy_synonyms():
    restored = MemoryStore([entity(synonyms=None)]).entities()[0]
    assert restored['synonyms'] == []
    assert restored['exact_synonyms'] == []


def test_regular_membership_wins_normalized_overlap_with_exact_aliases():
    original = entity(synonyms=['Old-Brand'],
                      exact_synonyms=['old brand', 'Fictional Ingredient', 'Zejula'])
    stored = {**original, **entity_alias_properties(original)}
    assert stored['exact_synonyms'] == ['Zejula']
    restored = MemoryStore([stored]).entities()[0]
    assert 'Old-Brand' in restored['synonyms']
    assert 'old brand' in restored['synonyms']
    assert 'Fictional Ingredient' in restored['synonyms']
    assert 'Zejula' not in restored['synonyms']


def test_graph_load_serializes_enriched_and_legacy_nodes_consistently():
    enriched = entity(synonyms=['Legacy brand'], exact_synonyms=['Zejula'])
    legacy = {**entity(synonyms=['Other brand']), 'uid': 'fiction:other'}
    originals = deepcopy([enriched, legacy])
    store = MemoryStore()
    store.load([enriched, legacy], [])
    rows = store.writes[0][1]['rows']
    assert rows[0]['synonyms'] == ['Legacy brand', 'Zejula']
    assert rows[0]['exact_synonyms'] == ['Zejula']
    assert rows[1]['synonyms'] == ['Other brand']
    assert rows[1]['exact_synonyms'] == []
    assert [enriched, legacy] == originals
