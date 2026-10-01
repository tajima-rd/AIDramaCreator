# core/genai/rag/lexical_retriever.py
"""
語による検索(BM25)。追加の依存も埋め込みのモデルも要らない。

語の切り出しはTokenizerで差し替えられる(既定はtokenizer.BigramTokenizer。日本語の形態素解析を使うなら
sudachi_tokenizer.SudachiTokenizer)。索引の断片と問いに同じ切り出しを使う(索引には語を保存せず、
検索を作るときに切り出す)。問いと資料の言語が違う場合は一致しないので、埋め込みによる検索と併用する
(hybrid_retriever)。
"""

import math
from collections import Counter
from typing import Optional

from .chunk_index import ChunkIndex
from .retriever import Retriever, SearchHit
from .tokenizer import BigramTokenizer, Tokenizer


class LexicalRetriever(Retriever):
    name = "lexical"

    def __init__(
        self, indexes: list[ChunkIndex], tokenizer: Optional[Tokenizer] = None, k1: float = 1.5, b: float = 0.75
    ):
        self.tokenizer = tokenizer if tokenizer is not None else BigramTokenizer()
        self.chunks = [c for index in indexes for c in index.chunks]
        self.k1, self.b = k1, b
        self.term_counts = [Counter(self.tokenizer.tokenize(c.text)) for c in self.chunks]
        self.lengths = [sum(counts.values()) for counts in self.term_counts]
        self.average_length = (sum(self.lengths) / len(self.lengths)) if self.lengths else 0.0
        document_frequency = Counter(term for counts in self.term_counts for term in counts)
        n = len(self.chunks)
        self.idf = {term: math.log(1 + (n - df + 0.5) / (df + 0.5)) for term, df in document_frequency.items()}
        self._vocabularies: dict[str, set[str]] = {}

    def vocabulary(self, source: str) -> set[str]:
        """1つの資料に現れる語。"""
        if source not in self._vocabularies:
            self._vocabularies[source] = {
                term for chunk, counts in zip(self.chunks, self.term_counts, strict=True) if chunk.source == source
                for term in counts
            }
        return self._vocabularies[source]

    def coverage(self, query: str, source: str) -> float:
        """問いの語のうち、資料に現れる語の割合(0〜1。問いに語が無ければ1)。言語の違いの見積もりに使う。"""
        terms = set(self.tokenizer.tokenize(query))
        return len(terms & self.vocabulary(source)) / len(terms) if terms else 1.0

    def scores(self, query: str) -> list[float]:
        terms = [t for t in set(self.tokenizer.tokenize(query)) if t in self.idf]
        result = []
        for counts, length in zip(self.term_counts, self.lengths):
            norm = self.k1 * (1 - self.b + self.b * length / self.average_length) if self.average_length else self.k1
            result.append(sum(self.idf[t] * counts[t] * (self.k1 + 1) / (counts[t] + norm) for t in terms if t in counts))
        return result

    def search(self, query: str, top_k: int = 8) -> list[SearchHit]:
        ranked = sorted(
            ((score, i) for i, score in enumerate(self.scores(query)) if score > 0), key=lambda item: (-item[0], item[1])
        )
        return [
            SearchHit(self.chunks[i], score, {self.name: rank}) for rank, (score, i) in enumerate(ranked[:top_k], start=1)
        ]
