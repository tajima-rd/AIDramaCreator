"""
日本語の形態素解析による語の切り出し(core.genai.rag.sudachi_tokenizer)。SudachiPyが無ければスキップする
(任意の依存、requirements/rag-ja.txt)。

- 日本語の文字の並びを、形態素の語(印付き、正規化した形、長い単位)と2文字ずつの語の両方にすること
- 助詞・助動詞・記号は語にせず、英字・数値は2文字ずつの切り出しと同じであること
- 形態素の語で、その語そのもの(「京都」)と関係の無い語の一部への一致(「東京都」)の点数の差が、
  2文字ずつだけの場合よりはっきり開くこと
- 表記の揺れ(「附属」と「付属」)が一致すること
"""

import pytest

pytest.importorskip("sudachipy")
pytest.importorskip("sudachidict_core")

from core.genai.rag import (
    BigramTokenizer,
    Chunk,
    ChunkIndex,
    LexicalRetriever,
    create_retriever,
)  # noqa: E402
from core.genai.rag.sudachi_tokenizer import MORPHEME_PREFIX, SudachiTokenizer  # noqa: E402


@pytest.fixture(scope="module")
def tokenizer():
    return SudachiTokenizer()


def _index(texts):
    chunks = [Chunk(f"doc#{i}", "doc", t, "text", f"page {i + 1}") for i, t in enumerate(texts)]
    return ChunkIndex(source="doc", chunks=chunks)


def test_morphemes_and_bigrams(tokenizer):
    tokens = tokenizer.tokenize("腎臓病の初期分布、CKD 3は0.25です。")
    morphemes = [t.removeprefix(MORPHEME_PREFIX) for t in tokens if t.startswith(MORPHEME_PREFIX)]
    assert morphemes == ["腎臓病", "初期", "分布"]  # 長い単位、助詞・助動詞・記号は除く
    assert {"腎臓", "臓病", "病の", "初期"} <= set(tokens)  # 2文字ずつの語も入る
    assert ["ckd", "3", "0.25"] == [
        t for t in tokens if t.isascii() and not t.startswith(MORPHEME_PREFIX)
    ]
    assert SudachiTokenizer(include_bigrams=False).tokenize("初期分布") == [
        MORPHEME_PREFIX + "初期",
        MORPHEME_PREFIX + "分布",
    ]
    with pytest.raises(ValueError):
        SudachiTokenizer(split_mode="X")


def test_word_itself_ranks_well_above_partial_match(tokenizer):
    index = _index(["京都の寺院の数", "東京都の寺院の数"])

    def ratio(t):
        hits = LexicalRetriever([index], t).search("京都", top_k=2)
        assert hits[0].chunk.text == "京都の寺院の数"
        return hits[0].score / hits[1].score

    assert ratio(BigramTokenizer()) < 1.2  # 2文字ずつだけでは、ほぼ同じ点数(長さの違いだけ)
    assert ratio(tokenizer) > 3


def test_orthographic_variants_match(tokenizer):
    def morphemes(text):
        return [t for t in tokenizer.tokenize(text) if t.startswith(MORPHEME_PREFIX)]

    assert morphemes("附属病院") == morphemes("付属病院")
    index = _index(["付属病院の受診者数", "大学の講義"])
    hits = create_retriever([index], tokenizer=tokenizer).search("附属", top_k=2)
    assert [h.chunk.text for h in hits] == ["付属病院の受診者数"]
