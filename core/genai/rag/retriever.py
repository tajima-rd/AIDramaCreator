# core/genai/rag/retriever.py
"""
検索の抽象の契約。問い(query)に近い断片を、近い順に返す。

具象は語による検索(lexical_retriever.LexicalRetriever、BM25。語の切り出しはtokenizer)・埋め込みによる検索
(embedding_retriever.EmbeddingRetriever)と、それらの順位を統合する検索
(hybrid_retriever.HybridRetriever)。既定の組み合わせはfactory.create_retrieverが作る。
"""

import abc
from dataclasses import dataclass, field

from .chunk import Chunk


@dataclass(frozen=True)
class SearchHit:
    chunk: Chunk
    score: float
    # 検索の方式ごとの順位(1始まり)。統合した検索で、どの方式で見つかったかを示す
    ranks: dict[str, int] = field(default_factory=dict)


class Retriever(abc.ABC):
    name: str = "retriever"

    @abc.abstractmethod
    def search(self, query: str, top_k: int = 8) -> list[SearchHit]:
        """queryに近い断片を、近い順に最大top_k件返す(一致するものが無ければ空)。"""
