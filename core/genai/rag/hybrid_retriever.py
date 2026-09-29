# core/genai/rag/hybrid_retriever.py
"""
複数の検索の結果を、順位で統合する(Reciprocal Rank Fusion)。

各方式の点数は尺度が違う(BM25は上限が無く、コサイン類似度は-1〜1)ため、点数ではなく順位を使う:
断片の点数 = Σ 1/(rank_constant + その方式での順位)。どの方式でも上位の断片が上に来て、
一方の方式でしか見つからない断片(言語の違う言い換え・表の数値)も残る。

search_manyは同じ統合を複数の問いに使う(決まった問い・利用者の発言等を1つの文にまとめると、
埋め込みの問いがぼやけるため、問いごとに探して順位で統合する)。per_source=Trueなら順位を資料ごとに付ける
(長い資料の断片が上位を占め、短い資料の断片が入らなくなるのを防ぐ。各資料で最も近い断片が同じ点数になる)。
"""

from .retriever import Retriever, SearchHit

DEFAULT_RANK_CONSTANT = 60


class HybridRetriever(Retriever):
    name = "hybrid"

    def __init__(self, retrievers: list[Retriever], rank_constant: int = DEFAULT_RANK_CONSTANT, candidates: int = 50):
        if not retrievers:
            raise ValueError("統合する検索がありません。")
        self.retrievers = retrievers
        self.rank_constant = rank_constant
        self.candidates = candidates  # 各方式から受け取る件数

    def search(self, query: str, top_k: int = 8) -> list[SearchHit]:
        scores: dict[str, float] = {}
        ranks: dict[str, dict[str, int]] = {}
        chunks = {}
        for retriever in self.retrievers:
            for hit in retriever.search(query, max(top_k, self.candidates)):
                key = hit.chunk.chunk_id
                rank = hit.ranks.get(retriever.name, 0)
                chunks[key] = hit.chunk
                scores[key] = scores.get(key, 0.0) + 1.0 / (self.rank_constant + rank)
                ranks.setdefault(key, {})[retriever.name] = rank
        ordered = sorted(scores, key=lambda key: -scores[key])[:top_k]
        return [SearchHit(chunks[key], scores[key], ranks[key]) for key in ordered]


def search_many(
    retriever: Retriever,
    queries: list[str],
    top_k: int = 8,
    rank_constant: int = DEFAULT_RANK_CONSTANT,
    per_source: bool = False,
    candidates: int = 50,
) -> list[SearchHit]:
    """問いごとに探し、順位で統合する(空の問いは飛ばす)。rankには問いの番号(q0・q1…)ごとの順位を入れる。

    per_source=Trueなら、各問いの結果の順位を資料ごとに数え直す(各問いからcandidates件受け取る)。
    """
    scores: dict[str, float] = {}
    ranks: dict[str, dict[str, int]] = {}
    chunks = {}
    for i, query in enumerate(q for q in queries if q.strip()):
        source_ranks: dict[str, int] = {}
        for overall, hit in enumerate(retriever.search(query, max(top_k, candidates) if per_source else top_k), 1):
            rank = overall
            if per_source:
                rank = source_ranks[hit.chunk.source] = source_ranks.get(hit.chunk.source, 0) + 1
            key = hit.chunk.chunk_id
            chunks[key] = hit.chunk
            scores[key] = scores.get(key, 0.0) + 1.0 / (rank_constant + rank)
            ranks.setdefault(key, {})[f"q{i}"] = rank
    ordered = sorted(scores, key=lambda key: -scores[key])[:top_k]
    return [SearchHit(chunks[key], scores[key], ranks[key]) for key in ordered]
