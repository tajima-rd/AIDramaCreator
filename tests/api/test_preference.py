# tests/api/test_preference.py
"""
プロジェクトの設定(Project > Preferences、routers/preference.py)の結合テスト。

- 未設定のプロジェクトは設定が空で、選べる提供元の一覧(URL・APIキーの要否)を返すこと
- 設定(文章生成は作品作り・作業補助の2つ)を保存すると project.yaml の genai セクションに書かれ、APIキーそのものは書かれないこと
- 不正な設定(未対応の提供元・モデルが空・必須のURLが無い)は400で、保存されないこと
- null を送るとその設定が消えること
- 接続テスト(文章生成・埋め込み)は、失敗しても例外ではなく ok=false と理由を返すこと
- 埋め込み(資料の検索)の設定も同じ形で保存・検証され、埋め込みに使えない提供元(Open WebUI等)は400であること
- モデル名の一覧・接続先URLの候補を返し、取得できない場合は理由つきの400であること
- APIキーは提供元と接続先から決まる名前で ~/.aidc/secrets.env(テストではtmp_path)に権限600で
  保存され、値は返さない(名前と伏せ字だけ)こと。シェル・プロセスの環境変数は読みも書きもしないこと
"""

import os
import stat

import yaml

from core.infra.store import secret_env_store
from core.service.process.genai import embedding_connection_tester, llm_connection_tester
from tests.conftest import parse_yaml


def _url(project):
    return f"/projects/{project.project_id}/preferences"


def _genai_section(project):
    with open(project.layout.project_yaml_path, encoding="utf-8") as f:
        return (yaml.safe_load(f) or {}).get("genai")


def test_get_default_preferences(client, project):
    resp = client.get(_url(project))
    assert resp.status_code == 200
    info = parse_yaml(resp)
    assert info["creative_llm"] is None and info["assistive_llm"] is None and info["tts"] is None
    clients = {c["name"]: c for c in info["llm_clients"]}
    assert set(clients) == {"Gemini", "LlamaCpp", "Ollama", "OpenWebUI"}
    assert clients["OpenWebUI"] == {"name": "OpenWebUI", "requires_api_url": True, "api_key_required": True}
    assert clients["Ollama"]["api_key_required"] is False
    assert [c["name"] for c in info["tts_clients"]] == ["Gemini"]
    assert info["embedding"] is None
    assert [c["name"] for c in info["embedding_clients"]] == ["Gemini", "LlamaCpp", "Ollama"]


def test_update_and_clear_preferences(client, project):
    body = {
        "creative_llm": {"client": "Gemini", "model": "gemini-3.5-flash"},
        "assistive_llm": {"client": "LlamaCpp", "model": " qwen ", "api_url": "http://localhost:8080"},
        "tts": {"client": "Gemini", "model": "gemini-3.8-flash-lite-tts", "api_url": ""},
    }
    resp = client.put(_url(project), json=body)
    assert resp.status_code == 200, resp.text
    info = parse_yaml(resp)
    assert info["assistive_llm"]["model"] == "qwen"  # 前後の空白は除く
    assert info["tts"]["api_url"] is None  # 空欄は未設定として扱う

    assert _genai_section(project) == {
        "creative_llm": {"client": "Gemini", "model": "gemini-3.5-flash"},
        "assistive_llm": {"client": "LlamaCpp", "model": "qwen", "api_url": "http://localhost:8080"},
        "tts": {"client": "Gemini", "model": "gemini-3.8-flash-lite-tts"},
    }
    info = parse_yaml(client.get(_url(project)))
    assert info["creative_llm"]["client"] == "Gemini" and info["assistive_llm"]["client"] == "LlamaCpp"

    resp = client.put(_url(project), json={"creative_llm": None, "assistive_llm": None, "tts": None})
    assert resp.status_code == 200
    assert _genai_section(project) is None


def test_update_rejects_invalid_settings(client, project):
    client.put(_url(project), json={"creative_llm": {"client": "Ollama", "model": "llama3.1:8b", "api_url": "http://localhost:11434"}})
    before = _genai_section(project)

    for llm in (
        {"client": "Unknown", "model": "m"},
        {"client": "Gemini", "model": "  "},
        {"client": "OpenWebUI", "model": "m"},  # URLが無い
    ):
        for key in ("creative_llm", "assistive_llm"):
            resp = client.put(_url(project), json={key: llm})
            assert resp.status_code == 400, (key, llm)
    resp = client.put(_url(project), json={"tts": {"client": "Ollama", "model": "m", "api_url": "http://x"}})
    assert resp.status_code == 400  # 音声合成に使えない提供元
    assert _genai_section(project) == before


def test_llm_connection_test(client, project, monkeypatch):
    resp = client.post(
        f"{_url(project)}/llm-test",
        json={"llm": {"client": "Ollama", "model": "m", "api_url": "http://127.0.0.1:9"}},
    )
    assert resp.status_code == 200
    result = parse_yaml(resp)
    assert result["ok"] is False and result["message"]

    class _FakeGenerator:
        def generate(self, prompt):
            return "OK"

    monkeypatch.setattr(llm_connection_tester, "build_text_generator", lambda project, role: _FakeGenerator())
    resp = client.post(f"{_url(project)}/llm-test", json={"llm": {"client": "Gemini", "model": "m"}})
    result = parse_yaml(resp)
    assert result["ok"] is True and result["response_text"] == "OK"
    assert _genai_section(project) is None  # 試すだけで保存はしない

    resp = client.post(f"{_url(project)}/llm-test", json={"llm": {"client": "OpenWebUI", "model": "m"}})
    assert resp.status_code == 400  # 設定そのものが不正


def test_embedding_setting(client, project):
    body = {
        "creative_llm": {"client": "Gemini", "model": "gemma-4-31b-it"},
        "embedding": {"client": "Ollama", "model": " nomic-embed-text ", "api_url": "http://localhost:11434"},
    }
    resp = client.put(_url(project), json=body)
    assert resp.status_code == 200, resp.text
    assert parse_yaml(resp)["embedding"] == {"client": "Ollama", "model": "nomic-embed-text", "api_url": "http://localhost:11434"}
    assert _genai_section(project)["embedding"] == {
        "client": "Ollama",
        "model": "nomic-embed-text",
        "api_url": "http://localhost:11434",
    }

    before = _genai_section(project)
    for embedding in (
        {"client": "OpenWebUI", "model": "m", "api_url": "http://localhost:3000"},  # 埋め込みに使えない
        {"client": "LlamaCpp", "model": "m"},  # URLが無い
    ):
        resp = client.put(_url(project), json={**body, "embedding": embedding})
        assert resp.status_code == 400, embedding
    assert _genai_section(project) == before

    # 送らなかった設定は消える(置き換え)
    client.put(_url(project), json={"creative_llm": body["creative_llm"]})
    assert "embedding" not in _genai_section(project)


def test_embedding_connection_test(client, project, monkeypatch):
    resp = client.post(
        f"{_url(project)}/embedding-test",
        json={"embedding": {"client": "LlamaCpp", "model": "m", "api_url": "http://127.0.0.1:9"}},
    )
    assert resp.status_code == 200
    result = parse_yaml(resp)
    assert result["ok"] is False and result["message"] and result["dimensions"] is None

    class _FakeEmbedder:
        def embed(self, texts, purpose):
            return [[0.1, 0.2, 0.3]]

    monkeypatch.setattr(embedding_connection_tester, "build_embedding_generator", lambda project: _FakeEmbedder())
    resp = client.post(f"{_url(project)}/embedding-test", json={"embedding": {"client": "Gemini", "model": "m"}})
    result = parse_yaml(resp)
    assert result["ok"] is True and result["dimensions"] == 3
    assert _genai_section(project) is None  # 試すだけで保存はしない

    resp = client.post(
        f"{_url(project)}/embedding-test",
        json={"embedding": {"client": "OpenWebUI", "model": "m", "api_url": "http://localhost:3000"}},
    )
    assert resp.status_code == 400  # 設定そのものが不正


def test_list_embedding_models(client, monkeypatch):
    calls = []

    def fake_available_models(kind, setting):
        calls.append((kind, type(setting).__name__))
        return ["bge-m3"]

    monkeypatch.setattr("core.service.process.genai.genai_setting_inspector.available_models", fake_available_models)
    body = {"kind": "embedding", "setting": {"client": "Ollama", "model": "", "api_url": "http://localhost:11434"}}
    resp = client.post("/preferences/models", json=body)
    assert resp.status_code == 200 and parse_yaml(resp)["models"] == ["bge-m3"]
    assert calls == [("embedding", "EmbeddingSetting")]


def test_unknown_project_returns_404(client):
    resp = client.get("/projects/00000000-0000-0000-0000-000000000000/preferences")
    assert resp.status_code == 404


def test_list_models(client, monkeypatch):
    # 取得できない(ここではURLが無い)は理由つきの400
    resp = client.post("/preferences/models", json={"kind": "llm", "setting": {"client": "Ollama", "model": ""}})
    assert resp.status_code == 400 and "API URL" in resp.json()["detail"]

    calls = []

    def fake_list_models(kind, setting):
        calls.append((kind, setting))
        return ["model-a", "model-b"]

    monkeypatch.setattr("core.service.process.genai.genai_setting_inspector.available_models", fake_list_models)
    body = {"kind": "llm", "setting": {"client": "Ollama", "model": "", "api_url": " http://localhost:11434 "}}
    resp = client.post("/preferences/models", json=body)
    assert resp.status_code == 200
    assert parse_yaml(resp)["models"] == ["model-a", "model-b"]
    # 空白・空欄はそろえてから問い合わせる
    assert calls[0][1].api_url == "http://localhost:11434"


def test_api_url_candidates(client, monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "0.0.0.0:11500")
    monkeypatch.setattr(
        "core.genai.openai_compatible.server_inspector.is_reachable",
        lambda url, path, timeout=2.0: url == "http://localhost:11434",
    )
    resp = client.get("/preferences/api-url-candidates", params={"client": "Ollama"})
    assert resp.status_code == 200
    assert parse_yaml(resp)["candidates"] == [
        {"url": "http://localhost:11434", "source": "default", "reachable": True},
        {"url": "http://localhost:11500", "source": "OLLAMA_HOST", "reachable": False},
    ]
    assert parse_yaml(client.get("/preferences/api-url-candidates", params={"client": "Gemini"}))["candidates"] == []


def test_api_key(client, project, monkeypatch):
    # 名前は提供元と接続先から決まり、シェルの環境変数は読まない
    monkeypatch.setenv("GEMINI_API_KEY", "from-shell")
    monkeypatch.setenv("AIDC_GEMINI_API_KEY", "from-shell")
    resp = client.get("/preferences/api-key", params={"client": "Gemini"})
    assert parse_yaml(resp) == {"name": "AIDC_GEMINI_API_KEY", "required": True, "available": False, "masked": None}

    resp = client.put("/preferences/api-key", json={"client": "Gemini", "value": " abcd-1234-efgh-5678 "})
    assert resp.status_code == 200
    assert parse_yaml(resp) == {
        "name": "AIDC_GEMINI_API_KEY", "required": True, "available": True, "masked": "abcd…5678"
    }
    assert "abcd-1234-efgh-5678" not in resp.text
    assert os.environ["AIDC_GEMINI_API_KEY"] == "from-shell"  # プロセスの環境変数には入れない

    # 同じ種類のサーバーでも、接続先ごとに別のキー(手元のホスト名はそろえる)
    resp = client.put(
        "/preferences/api-key",
        json={"client": "LlamaCpp", "api_url": "http://127.0.0.1:8080/v1/chat/completions", "value": "1234"},
    )
    assert parse_yaml(resp)["name"] == "AIDC_LLAMACPP_LOCALHOST_8080_API_KEY"
    local = parse_yaml(client.get("/preferences/api-key", params={"client": "LlamaCpp", "api_url": "http://localhost:8080"}))
    assert local == {"name": "AIDC_LLAMACPP_LOCALHOST_8080_API_KEY", "required": False, "available": True, "masked": "****"}
    remote = parse_yaml(client.get("/preferences/api-key", params={"client": "LlamaCpp", "api_url": "https://llama.example"}))
    assert remote["name"] == "AIDC_LLAMACPP_LLAMA_EXAMPLE_API_KEY" and remote["available"] is False

    path = secret_env_store.SECRETS_PATH
    assert path.startswith(str(os.path.dirname(os.path.dirname(project.layout.root_dir))))  # tmp_path配下
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert secret_env_store.load_saved() == {
        "AIDC_GEMINI_API_KEY": "abcd-1234-efgh-5678",
        "AIDC_LLAMACPP_LOCALHOST_8080_API_KEY": "1234",
    }

    for bad in (
        {"client": "Unknown", "value": "x"},
        {"client": "LlamaCpp", "value": "x"},  # 接続先が無いと名前が決まらない
        {"client": "Gemini", "value": "  "},
        {"client": "Gemini", "value": "a\nb"},
    ):
        assert client.put("/preferences/api-key", json=bad).status_code == 400, bad
    assert len(secret_env_store.load_saved()) == 2
