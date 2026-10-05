"""Lazy CPU embeddings; model and hub caches stay inside the repository."""

import os

import numpy as np

from medkg.config import ROOT


class Embeddings:
    def __init__(self):
        self.model = None

    def encode(self, texts: list[str]) -> np.ndarray:
        if self.model is None:
            os.environ.setdefault('HF_HOME', str(ROOT/'.cache/huggingface'))
            from fastembed import TextEmbedding
            self.model = TextEmbedding('BAAI/bge-small-en-v1.5',
                                       cache_dir=str(ROOT/'.cache/fastembed'), threads=2)
        vectors = np.asarray(list(self.model.embed(texts, batch_size=64)), dtype=np.float32)
        return vectors / np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)
