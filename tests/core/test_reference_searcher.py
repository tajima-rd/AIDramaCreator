# tests/core/test_reference_searcher.py
"""
参考資料の索引の保存と使い回し(core.service.process.genai.reference_searcher)。

- 保存済みの索引は、資料の中身・名前・埋め込みのモデルが同じなら使い回し、違えば作り直す
- 埋め込みの設定が無いときは、保存済みの索引の埋め込みを使わない(語による検索だけ)
- 索引・資料の言語はDatasetの改名・削除に付いていく
- 資料の言語と決まった問いの訳は資料ごとに1回だけ生成AIに頼み、足りない問いだけ追加で訳させ、資料が
  変われば判定し直す。発言の検索語は、発言と違う言語の資料があるときだけ作らせる
"""

import os

from core.genai import EmbeddingGenerator
from core.genai.rag import LexicalRetriever
from core.infra.store.dataset_file_store import (
    index_path,
    language_path,
    remove_dataset_files,
    rename_dataset_files,
)
from core.prompt.reference_search import ReferenceLanguageResponse, SearchTermsResponse
from core.service.process.genai.reference_searcher import (
    load_or_build_index,
    message_search_terms,
    reference_language,
)

DATA = b"alpha,beta\n1,2\n"


class _Embedder(EmbeddingGenerator):
    def embed_texts(self, texts, purpose):
        return [[1.0, float(len(t))] for t in texts]


def test_index_is_reused_or_rebuilt(tmp_path):
    datasets_dir = str(tmp_path)
    path = index_path(datasets_dir, "t.csv")
    first = load_or_build_index(datasets_dir, "t.csv", DATA, None)
    assert os.path.isfile(path) and not first.has_embeddings
    mtime = os.path.getmtime(path)
    load_or_build_index(datasets_dir, "t.csv", DATA, None)
    assert os.path.getmtime(path) == mtime  # 同じなら使い回す

    embedded = load_or_build_index(datasets_dir, "t.csv", DATA, _Embedder("m1"))
    assert embedded.embedding_model == "m1"  # 埋め込みの無い索引は作り直す
    assert load_or_build_index(datasets_dir, "t.csv", DATA, _Embedder("m2")).embedding_model == "m2"
    assert not load_or_build_index(
        datasets_dir, "t.csv", DATA, None
    ).has_embeddings  # 設定が無ければ使わない

    changed = load_or_build_index(datasets_dir, "t.csv", b"gamma\n3\n", None)
    assert changed.is_current(b"gamma\n3\n")  # 資料が変われば作り直す
    assert load_or_build_index(datasets_dir, "t.csv", DATA, None).is_current(DATA)


def test_index_follows_rename_and_delete(tmp_path):
    datasets_dir = str(tmp_path)
    (tmp_path / "t.csv").write_bytes(DATA)
    index = load_or_build_index(datasets_dir, "t.csv", DATA, None)
    reference_language(datasets_dir, index, DATA, ["q"], _Translator())
    rename_dataset_files(datasets_dir, "t.csv", "u.csv")
    assert not os.path.exists(index_path(datasets_dir, "t.csv"))
    assert os.path.isfile(index_path(datasets_dir, "u.csv")) and os.path.isfile(
        language_path(datasets_dir, "u.csv")
    )
    # 改名した索引は名前(断片の場所の見出しに使う)が違うため、使うときに作り直す
    assert load_or_build_index(datasets_dir, "u.csv", DATA, None).source == "u.csv"
    remove_dataset_files(datasets_dir, "u.csv")
    assert not os.path.exists(index_path(datasets_dir, "u.csv"))
    assert not os.path.exists(language_path(datasets_dir, "u.csv"))


class _Translator:
    """日本語の資料として判定し、問いに「訳」を付けて返す偽の生成AI。"""

    def __init__(self):
        self.requests = []

    def generate_structured(self, prompt, schema, *, system_instruction=None, attachments=None):
        self.requests.append((schema, prompt))
        if schema is ReferenceLanguageResponse:
            queries = [
                line.split(". ", 1)[1]
                for line in prompt.split("## Search queries\n")[1].splitlines()
            ]
            return ReferenceLanguageResponse(
                language="Japanese", queries=[f"訳:{q}" for q in queries]
            )
        return SearchTermsResponse(queries=[{"language": "Japanese", "query": "開始時点の分布"}])


def test_reference_language_is_cached(tmp_path):
    datasets_dir = str(tmp_path)
    data = "病期,割合\n1,3%\n".encode()
    index = load_or_build_index(datasets_dir, "j.csv", data, None)
    translator = _Translator()
    first = reference_language(datasets_dir, index, data, ["a", "b"], translator)
    assert first.language == "Japanese" and first.queries == {"a": "訳:a", "b": "訳:b"}
    assert "## Beginning of the document" in translator.requests[0][1]  # 初回は資料の冒頭で判定する

    assert reference_language(datasets_dir, index, data, ["b", "a"], translator) == first
    assert len(translator.requests) == 1  # 訳済みなら呼ばない
    more = reference_language(datasets_dir, index, data, ["a", "c"], translator)
    assert more.queries == {"a": "訳:a", "b": "訳:b", "c": "訳:c"}
    assert (
        "## Beginning of the document" not in translator.requests[1][1]
    )  # 足りない問いだけ訳させる
    assert (
        "1. c" in translator.requests[1][1]
        and "a" not in translator.requests[1][1].split("queries")[1]
    )

    changed = "病期,割合\n2,34%\n".encode()
    reference_language(
        datasets_dir,
        load_or_build_index(datasets_dir, "j.csv", changed, None),
        changed,
        ["a"],
        translator,
    )
    assert "## Beginning of the document" in translator.requests[2][1]  # 資料が変われば判定し直す


def test_message_search_terms_only_for_other_languages(tmp_path):
    data = "開始時点の病期の分布は、病期1が3%、病期2が34%であった。".encode()
    index = load_or_build_index(str(tmp_path), "j.csv", data, None)
    lexical = LexicalRetriever([index])
    translator = _Translator()
    languages = {"j.csv": "Japanese"}
    assert (
        message_search_terms(
            "病期の分布を提案してください", [index], languages, lexical, translator
        )
        == []
    )
    assert translator.requests == []  # 同じ言語なら呼ばない
    terms = message_search_terms(
        "Please propose the distribution of stages", [index], languages, lexical, translator
    )
    assert terms == ["開始時点の分布"]
    assert "Japanese" in translator.requests[0][1]
