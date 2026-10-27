"""Lazy CPU embeddings; model and hub caches stay inside the repository."""

import os

import numpy as np

from medkg.config import ROOT


class Embeddings:
    def __init__(self, threads: int = 2):
        if not 1<=threads<=4:
            raise ValueError('CPU embedding threads must be between one and four')
        self.threads = threads
        self.model = None

    def encode(self, texts: list[str]) -> np.ndarray:
        if self.model is None:
            os.environ.setdefault('HF_HOME', str(ROOT/'.cache/huggingface'))
            from fastembed import TextEmbedding
            self.model = TextEmbedding('BAAI/bge-small-en-v1.5',
                                       cache_dir=str(ROOT/'.cache/fastembed'), threads=self.threads)
        vectors = np.asarray(list(self.model.embed(texts, batch_size=64)), dtype=np.float32)
        return vectors / np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)


class Reranker:
    """Lazy CPU cross-encoder (D115), e.g. Xenova/ms-marco-MiniLM-L-6-v2: one relevance
    score per (query, passage) pair."""

    def __init__(self, threads: int = 2):
        if not 1<=threads<=4:
            raise ValueError('CPU reranking threads must be between one and four')
        self.threads = threads
        self.name, self.model = None, None

    def load(self, name: str):
        os.environ.setdefault('HF_HOME', str(ROOT/'.cache/huggingface'))
        from fastembed.rerank.cross_encoder import TextCrossEncoder
        return TextCrossEncoder(name, cache_dir=str(ROOT/'.cache/fastembed'), threads=self.threads)

    def scores(self, name: str, query: str, passages: list[str]) -> list[float]:
        if self.model is None or self.name != name:
            self.model, self.name = self.load(name), name
        return [float(s) for s in self.model.rerank(query, passages)]
