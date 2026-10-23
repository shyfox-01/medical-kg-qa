"""Exact-only aliases across scoring, cached evidence, parsing and embeddings."""

import json

import numpy as np
import pytest

from eval.score import Vocabulary
from medkg.ingest import medlineplus, openfda
from medkg.ingest.extract import cached_edge_supported
from medkg.qa.linker import Linker
from medkg.qa.verify import entities_in_text
from medkg_data.alias_policy import allowed_names, exact_names, is_excluded
from scripts import embed_entities


def drug() -> dict:
    return {'uid': 'DrugBank:fiction', 'label': 'Drug', 'name': 'niraparib',
            'synonyms': ['Regular alias'], 'exact_synonyms': ['Zejula', 'Aster Brand']}


def test_exact_names_are_optional_and_do_not_expand_allowed_names():
    entity = drug()
    assert allowed_names(entity) == ['niraparib', 'Regular alias']
    assert exact_names(entity) == ['niraparib', 'Regular alias', 'Zejula', 'Aster Brand']
    assert exact_names({**entity, 'exact_synonyms': None}) == allowed_names(entity)


def test_scorer_and_answer_verifier_extract_exact_only_alias():
    entity = drug()
    assert Vocabulary([entity]).extract('Zejula is recorded.') == {entity['uid']}
    assert entities_in_text('Zejula is recorded.', Linker([entity])) == {entity['uid']}


def test_hetastarch_is_quarantined_in_both_alias_fields_and_scorer():
    entity = {'uid': 'DrugBank:DB09111', 'label': 'Drug', 'name': 'Pentastarch',
              'synonyms': ['Hetastarch'], 'exact_synonyms': ['HETASTARCH', 'Safe brand']}
    assert is_excluded(entity['uid'], 'Hetastarch')
    assert allowed_names(entity) == ['Pentastarch']
    assert exact_names(entity) == ['Pentastarch', 'Safe brand']
    assert Linker([entity]).link('Hetastarch') == []
    assert Vocabulary([entity]).extract('Hetastarch') == set()
    assert entity['synonyms'] == ['Hetastarch']


def test_cached_quote_supports_exact_alias_but_not_quarantined_identity():
    entity = drug()
    disease = {'uid': 'MONDO:fiction', 'label': 'Disease', 'name': 'Fictional condition'}
    quote = 'Zejula is contraindicated for Fictional condition.'
    edge = {'a': entity['uid'], 'b': disease['uid'], 'type': 'CONTRAINDICATED_FOR',
            'quote': quote}
    assert cached_edge_supported(edge, {'text': quote},
                                 {entity['uid']: entity, disease['uid']: disease})
    rejected = {'uid': 'DrugBank:DB09111', 'label': 'Drug', 'name': 'Pentastarch',
                'synonyms': ['Hetastarch']}
    quote = 'Hetastarch is contraindicated for Fictional condition.'
    assert not cached_edge_supported({**edge, 'a': rejected['uid'], 'quote': quote},
                                     {'text': quote},
                                     {rejected['uid']: rejected, disease['uid']: disease})


@pytest.mark.parametrize('name,linked', [('Aster Brand', True), ('Brand Aster', False)])
def test_fda_exact_alias_does_not_enter_fuzzy_lookup_or_get_promoted(name, linked):
    entity = drug()
    records = [{'results': [{'id': 'fiction', 'openfda': {
        'generic_name': [name], 'brand_name': ['Aster Brand'] if linked else []},
        'description': ['Fictional label.']}]}]
    documents, _, _ = openfda.parse(records, [entity], 'fixture')
    assert bool(documents) is linked
    if linked:
        assert documents[0]['about'] == [entity['uid']]
    assert entity['synonyms'] == ['Regular alias']
    assert entity['exact_synonyms'] == ['Zejula', 'Aster Brand']


def test_fda_unsafe_brand_cleanup_includes_exact_only_aliases():
    entity = drug()
    other = {'uid': 'DrugBank:other', 'label': 'Drug', 'name': 'Other ingredient',
             'synonyms': []}
    records = [{'results': [{'id': 'combination', 'openfda': {
        'generic_name': ['niraparib', 'Other ingredient'], 'brand_name': ['Aster Brand']}}]}]
    openfda.parse(records, [entity, other], 'fixture')
    assert entity['exact_synonyms'] == ['Zejula']
    assert Linker([entity, other]).link('Aster Brand') == []


def test_medlineplus_title_uses_exact_names(tmp_path):
    path = tmp_path/'topics.xml'
    path.write_text('<health-topics><health-topic id="1" language="English" '
                    'title="Exact topic"><full-summary>Topic text.</full-summary>'
                    '</health-topic></health-topics>', encoding='utf8')
    entity = {'uid': 'MONDO:fiction', 'label': 'Disease', 'name': 'Fictional condition',
              'exact_synonyms': ['Exact topic']}
    documents, _ = medlineplus.parse(path, [entity], {}, 'fixture')
    assert documents[0]['about'] == [entity['uid']]


def test_alias_embedding_builder_never_encodes_exact_only_names(tmp_path, monkeypatch):
    processed = tmp_path/'data/processed'
    processed.mkdir(parents=True)
    (processed/'entities.json').write_text(json.dumps([drug()]), encoding='utf8')
    encoded = []

    class FakeEmbeddings:
        def encode(self, texts):
            encoded.extend(texts)
            return np.zeros((len(texts), 384), dtype=np.float32)

    monkeypatch.setattr(embed_entities, 'ROOT', tmp_path)
    monkeypatch.setattr(embed_entities, 'Embeddings', FakeEmbeddings)
    embed_entities.main()
    assert set(encoded) == {'niraparib', 'Regular alias'}
    aliases = json.loads((processed/'vector_aliases.json').read_text(encoding='utf8'))
    assert {row['text'] for row in aliases} == set(encoded)
