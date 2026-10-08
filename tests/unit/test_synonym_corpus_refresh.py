"""Alias-only refresh preserves unrelated text/vectors and rejects stale inputs."""

import json

import numpy as np
import pytest

from scripts.refresh_synonym_corpus import digest, refresh


def fixture(tmp_path):
    processed = tmp_path/'processed'
    processed.mkdir()
    old = [{'uid':'fiction:drug','name':'Asterol','label':'Drug','synonyms':[]}]
    previous = tmp_path/'previous.json'
    previous.write_text(json.dumps(old))
    new = [dict(old[0],synonyms=['Starbrand'])]
    (processed/'entities.json').write_text(json.dumps(new))
    (processed/'synonym_additions.jsonl').write_text('')
    rows = [{'uid':'text:1','text':'Unchanged document.'},
            {'uid':'vector-primekg:fiction:drug',
             'text':'Asterol. Also known as: none recorded. Asterol targets VELA (PrimeKG).'}]
    corpus = processed/'vector_corpus.jsonl'
    corpus.write_bytes(b''.join((json.dumps(r)+'\r\n').encode() for r in rows))
    vectors = np.zeros((2,384),dtype=np.float32)
    vectors[:,0] = 1
    np.save(processed/'vector_corpus.npy',vectors)
    (processed/'vector_progress.json').write_text(json.dumps(
        {'sha256':digest(corpus),'completed':2,'total':2}))
    return processed,previous


class Embedder:
    def __init__(self):
        self.texts = []

    def encode(self,texts):
        self.texts.extend(texts)
        result = np.zeros((len(texts),384),dtype=np.float32)
        result[:,1] = 1
        return result


def test_only_changed_alias_text_is_reencoded_and_originals_are_backed_up(tmp_path):
    processed,previous = fixture(tmp_path)
    original = (processed/'vector_corpus.jsonl').read_bytes()
    embedder = Embedder()
    report = refresh(processed,previous,tmp_path/'backup',embedder)
    assert report['changed_rows']==1 and report['reused_rows']==1
    assert embedder.texts==['Asterol. Also known as: Starbrand. Asterol targets VELA (PrimeKG).']
    assert (tmp_path/'backup/vector_corpus.jsonl').read_bytes()==original
    assert (processed/'vector_corpus.jsonl').read_bytes().splitlines()[0]==original.splitlines()[0]
    vectors = np.load(processed/'vector_corpus.npy')
    assert vectors[0,0]==1 and vectors[1,1]==1 and vectors[1,0]==0
    assert report['corpus_sha256']==digest(processed/'vector_corpus.jsonl')


@pytest.mark.parametrize('change',['stale_hash','name_change','wrong_previous_alias'])
def test_invalid_refresh_does_not_modify_corpus_or_vectors(tmp_path,change):
    processed,previous = fixture(tmp_path)
    if change=='stale_hash':
        (processed/'vector_corpus.jsonl').write_text('{"uid":"tampered"}\n')
    elif change=='name_change':
        entity = json.loads((processed/'entities.json').read_text())[0]
        entity['name'] = 'Brinex'
        (processed/'entities.json').write_text(json.dumps([entity]))
    else:
        entity = json.loads(previous.read_text())[0]
        entity['synonyms'] = ['Starbrand']
        previous.write_text(json.dumps([entity]))
    before = [digest(processed/name) for name in ('vector_corpus.jsonl','vector_corpus.npy')]
    with pytest.raises(ValueError):
        refresh(processed,previous,tmp_path/'backup',Embedder())
    assert before==[digest(processed/name) for name in ('vector_corpus.jsonl','vector_corpus.npy')]
