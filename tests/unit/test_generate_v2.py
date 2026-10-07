"""Structured v2 generator rules and deterministic-3.5 scoring (fictional data only)."""

import json
import random

from eval import generate_v2 as G
from eval.score import Vocabulary, score
from medkg_data.ontology import Term


def test_typo_swaps_two_interior_letters():
    wrong = G.typo('Asterolin', random.Random(1))
    assert wrong != 'Asterolin' and sorted(wrong) == sorted('Asterolin')
    assert wrong[0] == 'A' and wrong[-1] == 'n'
    assert G.typo('Short', random.Random(1)) is None


def test_paraphrase_must_keep_anchors_and_shape_cues():
    row = {'anchors': ['Orion fever', 'Asterol'], 'kind': 'list', 'shape': 'exclusion'}
    assert G.valid_paraphrase(row, 'For Orion fever, which drugs are not contraindicated with Asterol?')
    assert not G.valid_paraphrase(row, 'For Orion fever, which drugs are fine with Asterol?')
    assert not G.valid_paraphrase(row, 'Which drugs are not contraindicated in Orion fever?')
    count = {'anchors': ['Asterol'], 'kind': 'count'}
    assert not G.valid_paraphrase(count, 'Which conditions is Asterol indicated for?')


def test_graph_directions():
    edges = [{'a': 'drug:a', 'b': 'disease:x', 'type': 'INDICATED_FOR'},
             {'a': 'drug:a', 'b': 'drug:b', 'type': 'INTERACTS_WITH'}]
    graph = G.Graph([], edges)
    assert graph.targets('indications', 'drug:a') == {'disease:x'}
    assert graph.targets('drugs_for', 'disease:x') == {'drug:a'}
    assert graph.targets('interactions', 'drug:b') == {'drug:a'}
    assert G.single_query('drugs_for') == ('MATCH (a:Disease {uid:$uid})<-[:INDICATED_FOR]-(b:Drug) '
                                           'RETURN DISTINCT b.uid AS uid')


def test_hpo_qualifier_branch_maps_to_primekg_uids():
    hp = {'HP:0012823': Term(id='HP:0012823'), 'HP:0003593': Term(id='HP:0003593', parents=['HP:0012823']),
          'HP:0001250': Term(id='HP:0001250', parents=['HP:0000118'])}
    assert G.hpo_qualifiers(hp) >= {'HPO:12823', 'HPO:3593'} and 'HPO:1250' not in G.hpo_qualifiers(hp)


def test_fda_brands_keep_single_ingredient_prescription_brands(tmp_path):
    labels = [('drug:a', 'Starvia', 'ASTEROL', 'HUMAN PRESCRIPTION DRUG'),
              ('drug:b', 'Nightcare', 'BRINEX', 'HUMAN PRESCRIPTION DRUG'),      # product word
              ('drug:c', 'Combix', 'ASTEROL AND BRINEX', 'HUMAN PRESCRIPTION DRUG'),
              ('drug:d', 'Velora', 'VELORIN', 'HUMAN OTC DRUG'),
              ('drug:e', 'Asterol Forte', 'ASTEROL', 'HUMAN PRESCRIPTION DRUG')]
    for i, (uid, brand, generic, kind) in enumerate(labels):
        record = {'drug_uid': uid, 'results': [{'openfda': {'brand_name': [brand], 'generic_name': [generic],
                                                            'product_type': [kind]}}]}
        (tmp_path / f'{i}.json').write_text(json.dumps(record), encoding='utf8')
    assert G.fda_brands(tmp_path) == {'drug:a': {'Starvia'}}


def test_lay_names_skip_non_disease_topics_and_vague_words(tmp_path):
    xml = ('<health-topics>'
           '<health-topic title="Star Fever" language="English"><also-called>SF</also-called>'
           '<also-called>sky</also-called><also-called>Comet flu</also-called></health-topic>'
           '<health-topic title="Star Fever Medicines" language="English"><also-called>SFM</also-called></health-topic>'
           '</health-topics>')
    path = tmp_path / 'topics.xml'
    path.write_text(xml, encoding='utf8')
    documents = [{'source': 'medlineplus', 'title': 'Star Fever', 'about': ['disease:x']},
                 {'source': 'medlineplus', 'title': 'Star Fever Medicines', 'about': ['disease:x']}]
    assert G.lay_names(path, documents) == {'disease:x': {'Star Fever', 'SF', 'Comet flu'}}


ENTITIES = [{'uid': 'drug:a', 'label': 'Drug', 'name': 'Asterol', 'synonyms': []}] + [
    {'uid': f'drug:{i}', 'label': 'Drug', 'name': f'Drugname{chr(97 + i)}', 'synonyms': []} for i in range(18)]


def test_complete_long_list_passes_without_partial_notice():
    expected = [f'drug:{i}' for i in range(18)]
    answer = '\n'.join(f'- Drugname{chr(97 + i)}' for i in range(18))
    case = {'kind': 'list', 'expected': expected, 'anchors': ['Asterol'], 'recall_applicable': False}
    result = {'answer': answer, 'contexts': [{'uid': u} for u in expected]}
    assert score(case, result, Vocabulary(ENTITIES))['passed']
    shorter = {'answer': '\n'.join(answer.splitlines()[:10]), 'contexts': result['contexts']}
    assert not score(case, shorter, Vocabulary(ENTITIES))['passed']


def test_explicit_anchor_uids_are_not_counted_as_answers():
    case = {'kind': 'list', 'expected': ['drug:1'], 'anchors': ['Astreol'], 'anchor_uids': ['drug:a'],
            'recall_applicable': True}
    result = {'answer': 'Asterol interacts with Drugnameb.', 'contexts': [{'uid': 'drug:1'}, {'uid': 'drug:a'}]}
    assert score(case, result, Vocabulary(ENTITIES))['passed']
