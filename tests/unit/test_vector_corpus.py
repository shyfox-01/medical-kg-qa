"""Vector-control alias fairness and rebuild invalidation, using fictional records."""

import hashlib
import json
import sys

import numpy as np

from scripts import build_vector_corpus as builder


def test_mesh_priority_uses_only_catalog_aliases_and_deduplicates_before_limit():
    entity = {'name':'Asterol','synonyms':['Legacy name','Starbrand','STARBRAND','Asterol',
                                         *[f'Alias {i}' for i in range(25)]]}
    aliases = builder.prioritized_synonyms(entity,['Outside catalog','Starbrand','STARBRAND'])
    assert aliases[:2] == ['Starbrand','Legacy name']
    assert len(aliases) == 20
    assert 'Outside catalog' not in aliases and 'Asterol' not in aliases
    assert len({alias.casefold() for alias in aliases}) == 20


def test_no_additional_synonyms_and_mesh_alias_absent_from_catalog():
    assert builder.prioritized_synonyms({'name':'Asterol','synonyms':[]},['Old brand']) == []


def test_rebuild_reencodes_changed_paragraphs_instead_of_reusing_old_vectors(tmp_path,monkeypatch):
    processed = tmp_path/'data/processed'
    processed.mkdir(parents=True)
    nodes = [{'uid':'fiction:drug','name':'Asterol','synonyms':[]},
             {'uid':'fiction:disease','name':'Orion fever','synonyms':[]}]
    catalog = [dict(nodes[0],synonyms=['Legacy name','Starbrand']),nodes[1]]
    (processed/'entities.json').write_text(json.dumps(catalog))
    additions = [{'uid':'fiction:drug','alias':'Starbrand','source':'mesh:D900001'},
                 {'uid':'fiction:drug','alias':'Legacy name','source':'other:900001'}]
    (processed/'synonym_additions.jsonl').write_text('\n'.join(map(json.dumps,additions)))
    chunk = {'uid':'chunk:fiction','text':'A fictional public document.','source':'fictional'}
    (processed/'chunks.jsonl').write_text(json.dumps(chunk)+'\n')
    corpus = processed/'vector_corpus.jsonl'
    corpus.write_text(json.dumps(chunk)+'\n'+json.dumps({'uid':'vector-primekg:fiction:drug',
                      'text':'Asterol. Old relation paragraph.'})+'\n')
    old_hash = hashlib.sha256(corpus.read_bytes()).hexdigest()
    progress = processed/'vector_progress.json'
    progress.write_text(json.dumps({'sha256':old_hash,'completed':2,'total':2}))
    matrix = processed/'vector_corpus.npy'
    np.save(matrix,np.full((2,384),-99,dtype=np.float32))
    encoded = []

    class Embedder:
        def __init__(self,threads):
            assert threads == 4

        def encode(self,texts):
            encoded.extend(texts)
            return np.ones((len(texts),384),dtype=np.float32)

    monkeypatch.setattr(builder,'ROOT',tmp_path)
    monkeypatch.setattr(builder,'load_obo',lambda _: {})
    monkeypatch.setattr(builder,'read_graph',lambda *_: (nodes,[{
        'a':'fiction:drug','b':'fiction:disease','type':'INDICATED_FOR'}],{}))
    monkeypatch.setattr(builder,'Embeddings',Embedder)
    monkeypatch.setattr(sys,'argv',['build_vector_corpus','--rebuild','--threads','4'])
    builder.main()
    rows = [json.loads(line) for line in corpus.read_text().splitlines()]
    assert rows[0] == chunk
    assert 'Also known as: Starbrand, Legacy name.' in rows[1]['text']
    assert 'Asterol indicated for Orion fever (PrimeKG).' in rows[1]['text']
    assert 'Also known as: none recorded.' in rows[2]['text']
    assert encoded == [row['text'] for row in rows]
    assert np.load(matrix).shape == (3,384) and np.all(np.load(matrix) == 1)
    assert json.loads(progress.read_text()) == {
        'sha256':hashlib.sha256(corpus.read_bytes()).hexdigest(),'completed':3,'total':3}
    # A matching completed rebuild is resumable without additional embedding work.
    encoded.clear()
    builder.main()
    assert not encoded
