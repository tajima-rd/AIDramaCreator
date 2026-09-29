"""
埋め込みの生成器(core.genai)。実際のAPI・サーバーは呼ばず、送る内容と受け取り方を確かめる。

- OpenAI互換のサーバー: embeddings APIへ{"model", "input"}を送り、indexの順に並べ直して返すこと。
  文章が多ければ分けて送り、APIキー・次元を送ること
- factory: 埋め込みに使える提供元(Open WebUIは未確認のため除く)と、URL・キーの確認
- モデルの一覧: 埋め込み(kind="embedding")では、Geminiはembed_contentに対応するもの、
  OpenAI互換のサーバーは全てを返すこと
- Gemini: 役割(文書/問い)をtaskTypeで送ること(google-genaiがある場合)。文章ごとにContentを分けて送り、
  それでも1つにまとめて返すモデルでは1件ずつ埋め込むこと(「埋め込みの数が文章の数と合いません」の再発防止)
"""

from types import SimpleNamespace

import pytest

from core.genai import EmbeddingConfig, create_embedding_generator
from core.genai.factory import EMBEDDING_CLIENTS, list_models
from core.genai.gemini import model_lister
from core.genai.openai_compatible import OpenAiCompatibleEmbeddingGenerator
from core.genai.openai_compatible import generator as openai_compatible_generator
from core.genai.openai_compatible import server_inspector


@pytest.fixture
def posted(monkeypatch):
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append((url, headers, json))
        data = [{"index": i, "embedding": [float(i), float(len(text))]} for i, text in enumerate(json["input"])]
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"data": list(reversed(data))})

    monkeypatch.setattr(openai_compatible_generator.requests, "post", fake_post)
    return calls


def test_openai_compatible_embedding(posted):
    embedder = OpenAiCompatibleEmbeddingGenerator(
        "http://localhost:8080", "bge-m3", api_key="k", config=EmbeddingConfig(dimensions=2, query_prefix="q: ")
    )
    embedder.batch_size = 2
    vectors = embedder.embed(["a", "bb", "ccc"], "document")
    assert vectors == [[0.0, 1.0], [1.0, 2.0], [0.0, 3.0]]  # indexの順・2件ずつに分けて送った
    assert [c[2]["input"] for c in posted] == [["a", "bb"], ["ccc"]]
    url, headers, payload = posted[0]
    assert url == "http://localhost:8080/v1/embeddings" and headers["Authorization"] == "Bearer k"
    assert payload["model"] == "bge-m3" and payload["dimensions"] == 2
    embedder.embed(["x"], "query")
    assert posted[-1][2]["input"] == ["q: x"]
    assert OpenAiCompatibleEmbeddingGenerator("http://h/v1/embeddings", "m").url == "http://h/v1/embeddings"


def test_factory_embedding():
    assert EMBEDDING_CLIENTS == ("Gemini", "LlamaCpp", "Ollama")
    gen = create_embedding_generator("Ollama", "nomic-embed-text", api_url="http://localhost:11434/v1/chat/completions")
    assert isinstance(gen, OpenAiCompatibleEmbeddingGenerator)
    assert gen.url == "http://localhost:11434/v1/embeddings" and "Authorization" not in gen.headers
    with pytest.raises(ValueError):
        create_embedding_generator("LlamaCpp", "m")  # URLが無い
    with pytest.raises(ValueError):
        create_embedding_generator("OpenWebUI", "m", api_url="http://localhost:3000", api_key="k")  # 未対応
    with pytest.raises(ValueError):
        create_embedding_generator("Gemini", "gemini-embedding-2")  # キーが無い
    with pytest.raises(ValueError):
        list_models("other", "Gemini", api_key="k")


def test_list_embedding_models(monkeypatch):
    body = {"data": [{"id": "qwen"}, {"id": "bge-m3"}, {"id": "nomic-embed-text:latest"}]}
    monkeypatch.setattr(
        server_inspector.requests,
        "get",
        lambda url, headers, timeout: SimpleNamespace(raise_for_status=lambda: None, json=lambda: body),
    )
    assert list_models("embedding", "LlamaCpp", api_url="http://localhost:8080") == [
        "bge-m3",
        "nomic-embed-text:latest",
        "qwen",
    ]
    assert list_models("llm", "LlamaCpp", api_url="http://localhost:8080") == ["bge-m3", "qwen"]

    models = [
        {"name": "models/gemma-4-31b-it", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-embedding-2", "supportedGenerationMethods": ["embedContent"]},
    ]
    monkeypatch.setattr(model_lister, "fetch_models", lambda api_key: models)
    assert model_lister.list_models("k", "embedding") == ["gemini-embedding-2"]
    assert model_lister.list_models("k", "llm") == ["gemma-4-31b-it"]


def test_gemini_embedding_task_type(monkeypatch):
    pytest.importorskip("google.genai")
    from core.genai.gemini import generator as gemini_generator

    calls = []

    class _Models:
        def embed_content(self, model, contents, config):
            calls.append((model, list(contents), config))
            return SimpleNamespace(
                embeddings=[SimpleNamespace(values=[1.0, float(len(c.parts[0].text))]) for c in contents]
            )

    monkeypatch.setattr(gemini_generator.genai, "Client", lambda api_key: SimpleNamespace(models=_Models()))
    embedder = gemini_generator.GeminiEmbeddingGenerator("k", config=EmbeddingConfig(dimensions=768))
    assert embedder.embed(["ab"], "query") == [[1.0, 2.0]]
    model, contents, config = calls[0]
    assert model == "gemini-embedding-2" and [c.parts[0].text for c in contents] == ["ab"]
    assert config.task_type == "RETRIEVAL_QUERY" and config.output_dimensionality == 768


def test_gemini_embedding_separates_texts(monkeypatch):
    """複数の文章を1つの埋め込みにまとめて返すモデルでも、文章の数だけ埋め込みを返す。"""
    pytest.importorskip("google.genai")
    from core.genai.gemini import generator as gemini_generator

    calls = []

    class _Merging:
        def embed_content(self, model, contents, config):
            texts = [p.text for c in contents for p in c.parts]
            calls.append(texts)
            return SimpleNamespace(embeddings=[SimpleNamespace(values=[float(len("".join(texts)))])])

    monkeypatch.setattr(gemini_generator.genai, "Client", lambda api_key: SimpleNamespace(models=_Merging()))
    embedder = gemini_generator.GeminiEmbeddingGenerator("k")
    assert embedder.embed(["a", "bb", "ccc"], "document") == [[1.0], [2.0], [3.0]]
    assert calls == [["a", "bb", "ccc"], ["a"], ["bb"], ["ccc"]]  # まとめて送り、数が合わないので1件ずつ
