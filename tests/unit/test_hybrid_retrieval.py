"""Text chunks come from the vector and full-text indexes, merged by rank fusion (D115)."""

import numpy as np
import pytest

from medkg.retrieval import vector


class Store:
    def __init__(self, **rows):
        self.rows, self.calls = rows, []

    def read(self, query, params):
        self.calls.append((query, params))
        arm = 'dense' if 'db.index.vector' in query else 'sparse'
        return [dict(row) for row in self.rows.get(arm, [])][:params['limit']]


def chunk(uid):
    return {'uid': uid, 'text': f'Text of {uid}', 'source': 'medlineplus'}


@pytest.fixture(autouse=True)
def embedding(monkeypatch):
    monkeypatch.setattr(vector.EMBEDDER, 'encode', lambda texts: np.zeros((len(texts), 384), dtype=np.float32))


def test_a_chunk_both_indexes_return_outranks_chunks_only_one_returns():
    fused = vector.fuse([[chunk('a'), chunk('b'), chunk('c')], [chunk('c'), chunk('d')]])
    assert [row['uid'] for row in fused] == ['c', 'a', 'b', 'd']   # b and d tie at rank 2
    assert fused[0]['score'] == pytest.approx(1/63+1/61, abs=1e-6)


def test_ties_keep_the_vector_order_and_only_the_top_chunks_are_kept():
    fused = vector.fuse([[chunk(f'v{i}') for i in range(10)], [chunk(f'k{i}') for i in range(10)]], top=4)
    assert [row['uid'] for row in fused] == ['v0', 'k0', 'v1', 'k1']


def test_hybrid_search_queries_both_indexes_with_the_same_filters():
    store = Store(dense=[chunk('a'), chunk('b')], sparse=[chunk('b')])
    rows = vector.search(store, 'Asterol and Glimmer sign?', source='openfda', uids=['fiction:drug']).rows
    assert [row['uid'] for row in rows] == ['b', 'a']
    (dense_query, dense), (sparse_query, sparse) = store.calls
    assert "queryNodes('chunk_embedding'" in dense_query and dense['pool'] == 512
    assert "queryNodes('ft_chunk_text'" in sparse_query
    assert sparse['query'] == '"Asterol" OR "and" OR "Glimmer" OR "sign"'
    for params in (dense, sparse):
        assert params['source'] == 'openfda' and params['uids'] == ['fiction:drug']
        assert params['limit'] == vector.CANDIDATES


def test_a_query_without_words_skips_the_full_text_index():
    store = Store(dense=[chunk('a')])
    assert vector.sparse(store, '?? ...') == [] and store.calls == []
    assert [row['uid'] for row in vector.search(store, '?? ...').rows] == ['a']


def test_an_unknown_source_is_rejected_before_any_query():
    store = Store()
    with pytest.raises(ValueError):
        vector.search(store, 'Asterol', source='elsewhere')
    assert store.calls == []


class CrossEncoder:
    """Scores a passage by how often it contains the query's last word."""
    def rerank(self, query, passages):
        word = query.split()[-1]
        return [passage.count(word) for passage in passages]


def test_reranking_is_off_unless_a_model_is_configured(monkeypatch):
    monkeypatch.delenv('RERANK_MODEL', raising=False)
    monkeypatch.setattr(vector.RERANKER, 'load', lambda name: pytest.fail('no model may load'))
    store = Store(dense=[chunk(f'v{i}') for i in range(12)])
    assert len(vector.search(store, 'Asterol').rows) == vector.TOP


def test_a_configured_cross_encoder_reorders_the_fused_candidates_with_titles(monkeypatch):
    monkeypatch.setenv('RERANK_MODEL', 'fiction/cross-encoder')
    monkeypatch.setattr(vector.RERANKER, 'load', lambda name: CrossEncoder())
    monkeypatch.setattr(vector.RERANKER, 'model', None)
    rows = [{**chunk(f'v{i}'), 'title': 'Glimmer' if i == 11 else 'Other'} for i in range(12)]
    result = vector.search(Store(dense=rows), 'about Glimmer').rows
    assert result[0]['uid'] == 'v11' and len(result) == vector.TOP   # beyond the fused top 8
    assert result[0]['score'] == 1
