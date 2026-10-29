"""Star-map coordinates (D128) from a fictional catalog and fictional ontology terms."""

import base64

import numpy as np

from medkg_data.ontology import Term
from medkg_data.starmap import REGIONS, build, nearest, regions

HP = {'HP:0000707': Term('HP:0000707', 'Abnormality of the nervous system'),
      'HP:0001626': Term('HP:0001626', 'Abnormality of the cardiovascular system'),
      'HP:0025142': Term('HP:0025142', 'Constitutional symptom'),
      'HP:0000001': Term('HP:0000001', 'Fictional headache', parents=['HP:0000707']),
      'HP:0000002': Term('HP:0000002', 'Fictional fainting', parents=['HP:0000003', 'HP:0025142']),
      'HP:0000003': Term('HP:0000003', 'Fictional heart sign', parents=['HP:0001626'])}
MONDO = {'MONDO:0004995': Term('MONDO:0004995', 'cardiovascular disorder'),
         'MONDO:0000010': Term('MONDO:0000010', 'fictional heart disease', parents=['MONDO:0004995'])}
CATALOG = [{'uid': 'fiction:drug-a', 'label': 'Drug', 'name': 'Asterol', 'node_id': 'DBX1'},
           {'uid': 'fiction:drug-b', 'label': 'Drug', 'name': 'Brinex', 'node_id': 'DBX2'},
           {'uid': 'fiction:disease', 'label': 'Disease', 'name': 'Orion syndrome', 'node_id': '10'},
           {'uid': 'fiction:phenotype-a', 'label': 'Phenotype', 'name': 'Amber spots', 'node_id': '1'},
           {'uid': 'fiction:phenotype-b', 'label': 'Phenotype', 'name': 'Indigo spots', 'node_id': '2'},
           {'uid': 'fiction:gene', 'label': 'Gene', 'name': 'ORN1', 'node_id': '9'}]
EDGES = [{'a': 'fiction:drug-a', 'b': 'fiction:disease', 'type': 'INDICATED_FOR'},
         {'a': 'fiction:drug-a', 'b': 'fiction:phenotype-a', 'type': 'HAS_SIDE_EFFECT'},
         {'a': 'fiction:disease', 'b': 'fiction:gene', 'type': 'ASSOCIATED_WITH'}]


def test_the_nearest_system_wins_and_general_only_when_nothing_is_closer():
    assert REGIONS[nearest('HP:0000001', HP, {'HP:0000707': 0})] == 'Brain and nerves'
    table = {'HP:0001626': 5, 'HP:0025142': 16}
    # Constitutional is a parent and the heart a grandparent: the nearer one wins; at the same
    # distance a body system would come first.
    assert REGIONS[nearest('HP:0000002', HP, table)] == 'General'
    assert REGIONS[nearest('HP:0000003', HP, table)] == 'Heart and circulation'
    assert nearest('HP:9999999', HP, table) == -1


def test_a_drug_takes_the_region_of_its_indications():
    region = regions(CATALOG, EDGES, HP, MONDO)
    names = [REGIONS[r] if r >= 0 else None for r in region]
    assert names == ['Heart and circulation', None, 'Heart and circulation', 'Brain and nerves', 'General', None]


def test_the_payload_places_every_entity_once():
    payload, uids = build(CATALOG, EDGES, HP, MONDO)
    assert uids == [e['uid'] for e in CATALOG] and payload['count'] == len(CATALOG)
    pos = np.frombuffer(base64.b64decode(payload['pos']), dtype=np.float32).reshape(-1, 3)
    assert pos.shape == (6, 3) and np.isfinite(pos).all()
    assert list(np.frombuffer(base64.b64decode(payload['type']), dtype=np.uint8)) == [0, 0, 1, 2, 2, 3]
    assert payload['regions'] == REGIONS and payload['areas'] == []
    again, _ = build(CATALOG, EDGES, HP, MONDO)
    assert again['pos'] == payload['pos']
