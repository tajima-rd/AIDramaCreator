# core/genai/rag/embedding_retriever.py
"""
埋め込みによる検索。問いを埋め込み、索引の断片とのコサイン類似度で並べる。

言い換え・言語の違い(日本語の問いで英語の資料を探す等)に強いが、数値や表の見出しの一致には
語による検索のほうが強い(hybrid_retrieverで併用する)。索引を埋め込んだモデルと同じモデルで
問いを埋め込む必要があり、違えばValueError(黙って比べない)。
"""

import numpy as np

from ..generator import EmbeddingGenerator
from .chunk_index import ChunkIndex, normalized
from .retriever import Retriever, SearchHit


class EmbeddingRetriever(Retriever):
    name = "embedding"

    def __init__(self, indexes: list[ChunkIndex], embedder: EmbeddingGenerator):
        for index in indexes:
            if not index.has_embeddings:
                raise ValueError(f"索引に埋め込みがありません: {index.source}")
            if index.embedding_model != embedder.model_name:
                raise ValueError(
                    f"索引の埋め込みのモデル({index.embedding_model})と問いのモデル({embedder.model_name})が"
                    f"違います: {index.source}"
                )
        self.embedder = embedder
        self.chunks = [c for index in indexes if index.chunks for c in index.chunks]
        matrices = [index.vectors for index in indexes if index.chunks]
        self.vectors = np.vstack(matrices) if matrices else None

    def search(self, query: str, top_k: int = 8) -> list[SearchHit]:
        if self.vectors is None or not query.strip():
            return []
        query_vector = normalized(self.embedder.embed([query], "query"))[0]
        if query_vector.shape[0] != self.vectors.shape[1]:
            raise ValueError("問いの埋め込みの次元が索引と違います。")
        similarities = self.vectors @ query_vector
        order = np.argsort(-similarities, kind="stable")[:top_k]
        return [
            SearchHit(self.chunks[i], float(similarities[i]), {self.name: rank})
            for rank, i in enumerate(order, start=1)
        ]
