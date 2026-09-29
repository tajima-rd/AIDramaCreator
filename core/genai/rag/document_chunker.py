# core/genai/rag/document_chunker.py
"""
Blockの列を検索の単位(Chunk)に分ける。

- 本文(text): 段落(空行、無ければ改行)を単位に、max_charsを超えない長さまで続けてまとめる。
  続く本文のBlock(DOCXの段落等)もまとめる。場所が複数にまたがる断片のlocatorは「最初–最後」。
  前の断片の末尾(overlap文字まで)の段落を次の断片の先頭にも入れ、境目の文脈を失わない。
  1つの段落がmax_charsより長ければ、文の区切り(無ければ文字数)で分ける
- 表(table): 1つの表は1つの断片にし、max_charsを超える表は行で分けて、各断片に見出しの行を繰り返す
  (数値だけの行では何の値か分からないため)。表の題(Block.caption)も各断片の先頭に付ける。
  分けた断片のlocatorには行の範囲を付ける("table 3 rows 1-20")
"""

import re

from .chunk import Block, Chunk

DEFAULT_MAX_CHARS = 1500
DEFAULT_OVERLAP_CHARS = 200

# 文の区切り(日本語の句点、英語等の終止符+空白)
_SENTENCE_END = re.compile(r"(?<=[。．！？])|(?<=[.!?])\s+")


def _split_long(text: str, max_chars: int) -> list[str]:
    """max_charsより長い段落を、文の区切り(無ければ文字数)で分ける。"""
    pieces: list[str] = []
    current = ""
    for sentence in (s for s in _SENTENCE_END.split(text) if s and s.strip()):
        while len(sentence) > max_chars:
            if current:
                pieces.append(current)
                current = ""
            pieces.append(sentence[:max_chars])
            sentence = sentence[max_chars:]
        joined = f"{current} {sentence}".strip() if current else sentence.strip()
        if len(joined) > max_chars:
            pieces.append(current)
            current = sentence.strip()
        else:
            current = joined
    if current:
        pieces.append(current)
    return pieces


def _paragraphs(text: str, max_chars: int) -> list[str]:
    parts = re.split(r"\n\s*\n", text) if re.search(r"\n\s*\n", text) else text.split("\n")
    result: list[str] = []
    for part in (p.strip() for p in parts):
        if part:
            result += _split_long(part, max_chars) if len(part) > max_chars else [part]
    return result


def _span(first: str, last: str) -> str:
    return first if first == last else f"{first}–{last}"


def _text_chunks(units: list[tuple[str, str]], max_chars: int, overlap: int) -> list[tuple[str, str]]:
    """(段落, 場所)の列を、max_charsまでまとめて(本文, 場所)の列にする。"""
    results: list[tuple[str, str]] = []
    current: list[tuple[str, str]] = []
    size = 0
    fresh = 0  # currentのうち、前の断片に入っていない段落の数
    for unit in units:
        added = len(unit[0]) + (2 if current else 0)
        if current and size + added > max_chars:
            results.append(("\n\n".join(u[0] for u in current), _span(current[0][1], current[-1][1])))
            carried: list[tuple[str, str]] = []
            carried_size = 0
            for previous in reversed(current):
                if carried_size + len(previous[0]) > overlap or carried_size + len(previous[0]) + len(unit[0]) > max_chars:
                    break
                carried.insert(0, previous)
                carried_size += len(previous[0]) + 2
            current, size, fresh = carried, carried_size, 0
            added = len(unit[0]) + (2 if current else 0)
        current.append(unit)
        size += added
        fresh += 1
    if current and fresh:
        results.append(("\n\n".join(u[0] for u in current), _span(current[0][1], current[-1][1])))
    return results


def _table_chunks(block: Block, max_chars: int) -> list[tuple[str, str]]:
    """表を行で分ける(見出しの2行=見出しと区切りを各断片に繰り返す)。"""
    prefix = f"{block.caption}\n" if block.caption else ""
    lines = block.text.split("\n")
    if len(prefix) + len(block.text) <= max_chars or len(lines) <= 3:
        return [(prefix + block.text, block.locator)]
    header, rows = lines[:2], lines[2:]
    base = len(prefix) + sum(len(h) + 1 for h in header)
    results: list[tuple[str, str]] = []
    start = 0
    while start < len(rows):
        end, size = start, base
        while end < len(rows) and (end == start or size + len(rows[end]) + 1 <= max_chars):
            size += len(rows[end]) + 1
            end += 1
        text = prefix + "\n".join(header + rows[start:end])
        results.append((text, f"{block.locator} rows {start + 1}-{end}"))
        start = end
    return results


def chunk_blocks(
    blocks: list[Block],
    source: str,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap: int = DEFAULT_OVERLAP_CHARS,
) -> list[Chunk]:
    """Blockの列をChunkの列にする(資料の順を保つ)。空のBlockは除く。"""
    if max_chars <= 0 or overlap < 0:
        raise ValueError("max_charsは正、overlapは0以上にしてください。")
    pieces: list[tuple[str, str, str]] = []  # (本文, 種類, 場所)
    pending: list[tuple[str, str]] = []  # まとめ中の本文の段落と場所

    def flush() -> None:
        pieces.extend((text, "text", locator) for text, locator in _text_chunks(pending, max_chars, overlap))
        pending.clear()

    for block in blocks:
        if not block.text.strip():
            continue
        if block.kind == "table":
            flush()
            pieces.extend((text, "table", locator) for text, locator in _table_chunks(block, max_chars))
        else:
            pending.extend((p, block.locator) for p in _paragraphs(block.text, max_chars))
    flush()
    return [
        Chunk(chunk_id=f"{source}#{i}", source=source, text=text, kind=kind, locator=locator)
        for i, (text, kind, locator) in enumerate(pieces)
    ]
