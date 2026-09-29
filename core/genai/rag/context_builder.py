# core/genai/rag/context_builder.py
"""
検索の結果から、生成AIに渡す文脈(テキスト)を組み立てる。

各断片の前に見出し「### [資料の名前 場所]」を付け、生成AIが根拠の場所をそのまま示せるようにする。
max_charsを超えない所まで、近い順に入れる(入らない断片は飛ばして、後の短い断片は入れる)。
同じ資料の断片は、近い順ではなく資料の中の順に並べ直す(前後のつながりを読み取りやすいように)。
"""

from .retriever import SearchHit

DEFAULT_CONTEXT_CHARS = 12000


def select_hits(hits: list[SearchHit], max_chars: int = DEFAULT_CONTEXT_CHARS) -> list[SearchHit]:
    """文脈に入れる断片(近い順に、max_charsを超えない所まで)を、資料ごと・資料の中の順に並べて返す。"""
    selected: list[SearchHit] = []
    size = 0
    for hit in hits:
        added = len(section(hit)) + (2 if selected else 0)
        if size + added > max_chars:
            continue
        selected.append(hit)
        size += added
    first_seen = {}
    for hit in selected:
        first_seen.setdefault(hit.chunk.source, len(first_seen))
    return sorted(selected, key=lambda h: (first_seen[h.chunk.source], _position(h)))


def _position(hit: SearchHit) -> int:
    suffix = hit.chunk.chunk_id.rsplit("#", 1)[-1]
    return int(suffix) if suffix.isdigit() else 0


def section(hit: SearchHit) -> str:
    return f"### [{hit.chunk.label}]\n{hit.chunk.text}"


def build_context(hits: list[SearchHit], max_chars: int = DEFAULT_CONTEXT_CHARS) -> str:
    return "\n\n".join(section(hit) for hit in select_hits(hits, max_chars))
