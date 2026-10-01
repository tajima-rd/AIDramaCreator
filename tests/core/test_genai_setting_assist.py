"""
生成AIの設定の入力補助(Project > Preferences): モデル名の一覧と接続先URLの候補。
実際のAPI・サーバーは呼ばず、requestsを偽物に差し替える。

- Geminiの一覧はREST APIのページを辿り、generateContentに対応するものを用途で振り分けること
  (キーはURLではなくヘッダーで渡し、エラーはAPIのメッセージ付きのValueErrorになること)
- OpenAI互換のサーバーの一覧から埋め込み専用のモデルを除くこと
- 設定のapi_url・環境変数の値(スキームの省略・0.0.0.0・パス付き)をサーバーのURLにそろえること
"""

from types import SimpleNamespace

import pytest

from core.genai.factory import OPENAI_COMPATIBLE_SERVERS, _normalize_server_url, api_url_candidates
from core.genai.gemini import model_lister
from core.genai.openai_compatible import server_inspector
from core.genai.openai_compatible.server_inspector import server_base_url
from core.infra.store import secret_env_store
from core.project.project import LlmSetting
from core.service.process.genai.genai_setting_inspector import available_models


def _response(status, body):
    return SimpleNamespace(
        status_code=status, ok=status < 400, reason="reason", content=b"x", json=lambda: body
    )


def test_gemini_list_models(monkeypatch):
    pages = {
        None: {
            "models": [
                {
                    "name": "models/gemini-3.5-flash",
                    "supportedGenerationMethods": ["generateContent"],
                },
                {
                    "name": "models/gemini-3.8-flash-tts",
                    "supportedGenerationMethods": ["generateContent"],
                },
                {
                    "name": "models/gemini-3-pro-image",
                    "supportedGenerationMethods": ["generateContent"],
                },
            ],
            "nextPageToken": "p2",
        },
        "p2": {
            "models": [
                {
                    "name": "models/gemma-4-31b-it",
                    "supportedGenerationMethods": ["generateContent"],
                },
                {
                    "name": "models/gemini-embedding-2",
                    "supportedGenerationMethods": ["embedContent"],
                },
            ]
        },
    }
    calls = []

    def fake_get(url, headers, params, timeout):
        calls.append((url, headers, params))
        return _response(200, pages[params.get("pageToken")])

    monkeypatch.setattr(model_lister.requests, "get", fake_get)
    assert model_lister.list_models("k", "llm") == ["gemini-3.5-flash", "gemma-4-31b-it"]
    assert model_lister.list_models("k", "tts") == ["gemini-3.8-flash-tts"]
    assert calls[0][1] == {"x-goog-api-key": "k"} and "key" not in calls[0][2]

    monkeypatch.setattr(
        model_lister.requests,
        "get",
        lambda *a, **k: _response(400, {"error": {"message": "API key not valid."}}),
    )
    with pytest.raises(ValueError, match="API key not valid"):
        model_lister.list_models("bad", "llm")


def test_openai_compatible_list_models(monkeypatch):
    body = {"data": [{"id": "qwen"}, {"id": "nomic-embed-text:latest"}, {"id": "llama3.1:8b"}]}
    calls = []

    def fake_get(url, headers, timeout):
        calls.append((url, headers))
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: body)

    monkeypatch.setattr(server_inspector.requests, "get", fake_get)
    secret_env_store.save_secret("AIDC_OPENWEBUI_LOCALHOST_3000_API_KEY", "sk")
    setting = LlmSetting(
        client="OpenWebUI", model="", api_url="http://localhost:3000/api/chat/completions"
    )
    assert available_models("llm", setting) == ["llama3.1:8b", "qwen"]
    assert calls[0] == ("http://localhost:3000/api/models", {"Authorization": "Bearer sk"})

    with pytest.raises(ValueError):
        available_models("llm", LlmSetting(client="Ollama", model=""))  # URLが無い
    with pytest.raises(ValueError):
        available_models(
            "tts", LlmSetting(client="Ollama", model="", api_url="http://x")
        )  # 音声合成に使えない


def test_server_urls():
    assert (
        server_base_url("http://localhost:8080/", "/v1/chat/completions") == "http://localhost:8080"
    )
    assert server_base_url("https://h/v1/chat/completions", "/v1/chat/completions") == "https://h"
    assert (
        server_base_url("http://h:3000/api/chat/completions", "/api/chat/completions")
        == "http://h:3000"
    )

    ollama = OPENAI_COMPATIBLE_SERVERS["Ollama"]
    assert _normalize_server_url("127.0.0.1:11434", ollama) == "http://127.0.0.1:11434"
    assert _normalize_server_url("0.0.0.0", ollama) == "http://localhost:11434"
    assert (
        _normalize_server_url("https://llm.example/v1/chat/completions", ollama)
        == "https://llm.example"
    )


def test_api_url_candidates_prefers_reachable(monkeypatch):
    monkeypatch.setenv("LLAMA_API_URL", "https://llm.example/v1/chat/completions")
    monkeypatch.setattr(
        server_inspector, "is_reachable", lambda url, path, timeout=2.0: "localhost" in url
    )
    candidates = api_url_candidates("LlamaCpp")
    assert [(c.url, c.source, c.reachable) for c in candidates] == [
        ("http://localhost:8080", "default", True),
        ("https://llm.example", "LLAMA_API_URL", False),
    ]
    assert api_url_candidates("Gemini") == []
