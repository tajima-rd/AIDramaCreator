"""
資料の検索(core.genai.rag)。埋め込みは偽物(語の出現を数えるだけの生成器)に差し替える。

- 分割: 本文は段落単位でmax_charsまでまとめ、境目を重ねる。表は行で分けても見出しの行と題を保つ
- 語の切り出し: 英字は小文字の単語、数値は小数点・%を含めて1語、日本語は2文字ずつ
- 語による検索(BM25): 問いの語を含む断片が近い順に並び、一致しなければ空
- 埋め込みによる検索: 索引と同じモデルの問いだけを比べ、違うモデル・埋め込みの無い索引はValueError
- 順位の統合: 一方の方式でしか見つからない断片も残り、両方で上位の断片が上に来る。複数の問いも同じく
  順位で統合し、空の問いは飛ばす
- 索引の保存と読み込みで中身が変わらず、資料の変更をis_currentで確かめられること
- 文脈: 見出しに資料の名前と場所を付け、上限の長さを超えないこと
- 補足資料(DOCX、ゴールデン入力は読むだけ)で、表の題から表が見つかること
- 問いと資料の言語の違いの見積もり: 文字の種類が資料に無ければ違う。ラテン文字どうしは語の一致の割合で
  見分け、漢字・かなどうしは(話し言葉の言い回しが資料に無くても)同じとみなす
"""

import os

import numpy as np
import pytest

from core.genai import EmbeddingConfig, EmbeddingGenerator
from core.genai.rag import (
    Block,
    Chunk,
    ChunkIndex,
    EmbeddingRetriever,
    HybridRetriever,
    LexicalRetriever,
    build_context,
    chunk_blocks,
    create_retriever,
    index_document,
    language_differs,
    search_many,
)
from core.genai.rag.tokenizer import BigramTokenizer
from tests.conftest import REFERENCE_SAMPLE_DIR, requires_reference_samples

VOCABULARY = ["alpha", "beta", "gamma", "delta", "初期", "分布"]


class _CountingEmbedder(EmbeddingGenerator):
    """語彙ごとの出現を数えたベクトル(意味は持たないが、同じ語を含む文章が近くなる)。"""

    def __init__(self, model_name="counting", config=None):
        super().__init__(model_name, config)
        self.calls = []

    def embed_texts(self, texts, purpose):
        self.calls.append((purpose, list(texts)))
        return [[float(t.lower().count(word)) + 0.01 for word in VOCABULARY] for t in texts]


def _index(source, texts):
    """1つの文章を1つの断片にした索引(ページごと)。"""
    chunks = [
        Chunk(f"{source}#{i}", source, t, "text", f"page {i + 1}") for i, t in enumerate(texts)
    ]
    return ChunkIndex(source=source, chunks=chunks)


def tokenize(text):
    return BigramTokenizer().tokenize(text)


def test_tokenize():
    assert tokenize("CKD Stage 3: 0.25 and 3% (n=1,234)") == [
        "ckd",
        "stage",
        "3",
        "0.25",
        "and",
        "3%",
        "n",
        "1,234",
    ]
    assert tokenize("初期分布") == ["初期", "期分", "分布"]
    assert tokenize("状態A") == ["状態", "a"]
    assert tokenize("鍵") == ["鍵"]
    assert tokenize("ＣＫＤ ステージ３") == [
        "ckd",
        "ステ",
        "テー",
        "ージ",
        "3",
    ]  # 全角・半角をそろえる


def test_chunk_text_packs_paragraphs_with_overlap():
    blocks = [Block("aaaa\n\nbbbb\n\ncccc", "text", "page 1"), Block("dddd", "text", "page 2")]
    chunks = chunk_blocks(blocks, "doc", max_chars=10, overlap=4)
    assert [c.text for c in chunks] == ["aaaa\n\nbbbb", "bbbb\n\ncccc", "cccc\n\ndddd"]
    assert [c.locator for c in chunks] == ["page 1", "page 1", "page 1–page 2"]
    assert [c.chunk_id for c in chunks] == ["doc#0", "doc#1", "doc#2"]

    long = chunk_blocks(
        [Block("One two. Three four. Five six.", "text", "p")], "doc", max_chars=12, overlap=0
    )
    assert [c.text for c in long] == ["One two.", "Three four.", "Five six."]
    assert chunk_blocks([Block("  ", "text", "p")], "doc") == []
    with pytest.raises(ValueError):
        chunk_blocks([], "doc", max_chars=0)


def test_chunk_table_repeats_header_and_caption():
    table = "| state | share |\n| --- | --- |\n| A | 0.1 |\n| B | 0.2 |\n| C | 0.3 |"
    chunks = chunk_blocks(
        [Block(table, "table", "table 1", "Table 1. Shares")], "doc", max_chars=60
    )
    assert len(chunks) > 1 and all(c.kind == "table" for c in chunks)
    for c in chunks:
        assert c.text.startswith("Table 1. Shares\n| state | share |\n| --- | --- |\n")
    assert chunks[0].locator == "table 1 rows 1-1" and chunks[-1].locator.endswith("-3")
    body_rows = [line for c in chunks for line in c.text.split("\n")[3:]]
    assert body_rows == ["| A | 0.1 |", "| B | 0.2 |", "| C | 0.3 |"]

    small = chunk_blocks([Block(table, "table", "table 1")], "doc", max_chars=1000)
    assert [c.text for c in small] == [table] and small[0].locator == "table 1"


def test_lexical_search():
    retriever = LexicalRetriever(
        [_index("a.pdf", ["alpha beta", "gamma gamma", "delta"]), _index("b.pdf", ["beta gamma"])]
    )
    hits = retriever.search("gamma", top_k=5)
    assert [h.chunk.label for h in hits] == ["a.pdf page 2", "b.pdf page 1"]
    assert hits[0].ranks == {"lexical": 1} and hits[0].score > hits[1].score
    assert retriever.search("unknown") == [] and retriever.search("") == []
    assert LexicalRetriever([]).search("gamma") == []


def test_embedding_search_and_model_check():
    embedder = _CountingEmbedder()
    index = _index("a.pdf", ["alpha", "初期分布の表", "gamma"]).with_embeddings(embedder)
    assert embedder.calls[0][0] == "document" and index.embedding_model == "counting"
    assert np.allclose(np.linalg.norm(index.vectors, axis=1), 1)

    hits = EmbeddingRetriever([index], embedder).search("分布", top_k=1)
    assert embedder.calls[-1] == ("query", ["分布"])
    assert hits[0].chunk.text == "初期分布の表" and hits[0].ranks == {"embedding": 1}

    with pytest.raises(ValueError, match="モデル"):
        EmbeddingRetriever([index], _CountingEmbedder("other"))
    with pytest.raises(ValueError, match="埋め込みがありません"):
        EmbeddingRetriever([_index("b.pdf", ["alpha"])], embedder)


def test_embedding_prefix_by_purpose():
    embedder = _CountingEmbedder(
        config=EmbeddingConfig(document_prefix="doc: ", query_prefix="query: ")
    )
    embedder.embed(["alpha"], "document")
    embedder.embed(["alpha"], "query")
    assert embedder.calls == [("document", ["doc: alpha"]), ("query", ["query: alpha"])]
    assert embedder.embed([]) == []


def test_hybrid_merges_by_rank():
    embedder = _CountingEmbedder()
    # 「初期分布」は語による検索では英語の断片に一致しないが、埋め込み(偽物)では近い
    index = _index("a.pdf", ["alpha 初期分布", "beta beta", "gamma"]).with_embeddings(embedder)
    retriever = create_retriever([index], embedder)
    assert isinstance(retriever, HybridRetriever)
    hits = retriever.search("alpha beta", top_k=3)
    assert hits[0].ranks.keys() == {"lexical", "embedding"}
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)
    # 語による検索では見つからない「初期分布」も、埋め込みの順位で統合の結果に入る
    assert retriever.search("初期分布", top_k=1)[0].chunk.text == "alpha 初期分布"
    assert isinstance(
        create_retriever([index]), LexicalRetriever
    )  # 埋め込みが無ければ語による検索だけ


def test_search_many_merges_queries():
    retriever = create_retriever([_index("a.pdf", ["alpha", "beta", "alpha beta", "gamma"])])
    hits = search_many(retriever, ["alpha", "beta", "  "], top_k=4)
    assert hits[0].chunk.text == "alpha beta"  # 両方の問いで見つかる断片が上
    assert hits[0].ranks.keys() == {"q0", "q1"}
    assert {h.chunk.text for h in hits} == {
        "alpha",
        "beta",
        "alpha beta",
    }  # どちらか一方の問いの断片も残る
    assert search_many(retriever, [], top_k=4) == []


def test_index_save_load(tmp_path):
    data = b"alpha,beta\n1,2\n"
    embedder = _CountingEmbedder()
    index = index_document("t.csv", data, "csv", embedder=embedder)
    path = tmp_path / "indexes" / "t.index"
    index.save(path)
    assert path.exists()  # 拡張子を付け足さない
    loaded = ChunkIndex.load(path)
    assert loaded.chunks == index.chunks and loaded.source_hash == index.source_hash
    assert loaded.embedding_model == "counting" and np.allclose(loaded.vectors, index.vectors)
    assert loaded.is_current(data) and not loaded.is_current(b"changed")

    plain = index_document("t.csv", data, "csv")
    plain.save(tmp_path / "plain.index")
    assert not ChunkIndex.load(tmp_path / "plain.index").has_embeddings


def test_build_context_limits_and_orders():
    index = _index("a.pdf", ["gamma one", "gamma two", "gamma three"])
    hits = LexicalRetriever([index]).search("gamma three", top_k=3)
    context = build_context(hits)
    assert context.startswith("### [a.pdf page 1]\ngamma one")  # 同じ資料の断片は資料の中の順
    assert "### [a.pdf page 3]\ngamma three" in context
    limited = build_context(hits, max_chars=len("### [a.pdf page 3]\ngamma three"))
    assert limited == "### [a.pdf page 3]\ngamma three"  # 最も近い断片だけが入る
    assert build_context([]) == ""


@requires_reference_samples
def test_supplement_table_found_by_caption():
    with open(
        os.path.join(REFERENCE_SAMPLE_DIR, "389456.docx"), "rb"
    ) as f:  # ゴールデン入力は読むだけ
        index = index_document("supplement.docx", f.read(), "docx")
    hits = create_retriever([index]).search("Health state at diagnosis", top_k=3)
    top = hits[0].chunk
    assert top.kind == "table" and top.locator.startswith("table ")
    assert top.text.startswith("Supplementary Table 3.") and "| CKD 1* | 3% |" in top.text


def test_language_differs():
    english = _index(
        "en.pdf", ["The model uses a cycle length of one month and a lifetime horizon."] * 3
    )
    japanese = _index(
        "ja.pdf", ["本研究のモデルのサイクルの長さは1か月、観察期間は生涯とした。Markov model"] * 3
    )
    german = _index("de.pdf", ["Die Zykluslänge des Modells beträgt einen Monat."] * 3)
    lexical = LexicalRetriever([english, japanese, german])

    def differs(query):
        return {
            i.source for i in (english, japanese, german) if language_differs(query, i, lexical)
        }

    assert differs("時間の刻みを提案してください") == {
        "en.pdf",
        "de.pdf",
    }  # 同じ日本語は言い回しが違っても同じ
    assert differs("propose the cycle length of the model") == {
        "ja.pdf",
        "de.pdf",
    }  # 英字を含む日本語の資料も
    assert (
        differs("ok") == set()
    )  # 語が少なければ語の一致の割合では見分けない(日本語の資料にも英字がある)
    assert differs("") == set()


def test_search_many_per_source():
    """資料ごとに順位を付けると、長い資料の断片に締め出されていた短い資料の断片が上位に入る。"""
    long = _index("long.pdf", [f"alpha alpha alpha {i}" for i in range(10)])
    short = _index("short.docx", ["alpha table"])
    retriever = create_retriever([long, short])
    assert "short.docx" not in {h.chunk.source for h in search_many(retriever, ["alpha"], top_k=3)}
    hits = search_many(retriever, ["alpha"], top_k=3, per_source=True)
    assert hits[0].chunk.source != hits[1].chunk.source and "short.docx" in {
        h.chunk.source for h in hits[:2]
    }
