"""
OpenAI互換のサーバーによる文章生成(core.genai.openai_compatible)と、factoryからの作り方。
実際のサーバーは呼ばず、requests.postを偽物に差し替えて、送る内容と受け取り方を確かめる。

- サーバーのURLでも、エンドポイントまで含むURLでも同じ所へ送ること
- system指示・会話履歴・設定・APIキーがOpenAI互換の形で送られること
- 構造化出力がjson_schemaで要求され、pydanticのスキーマに詰めて返ること。出力が長さの上限で切れたら
  (finish_reason=length)不正なJSONの誤りではなくOutputTruncatedErrorになること
- 対応しない機能(思考レベル・URLの読み込み・PDFの添付)はValueErrorになること
- factoryはclient(LlamaCpp/Ollama/OpenWebUI)ごとにパスとAPIキーの扱いを変え、api_urlを必須とすること
- APIキーの名前は提供元と接続先から決まり(手元のホスト名はそろえる)、保存したキーだけを使うこと
"""

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from core.genai import Attachment, Message, OutputTruncatedError, TextConfig, ThinkingLevel
from core.genai.openai_compatible import (
    OpenAiCompatibleEmbeddingGenerator,
    OpenAiCompatibleTextGenerator,
)
from core.genai.openai_compatible import generator as openai_compatible_generator
from core.infra.store import secret_env_store
from core.project.project import EmbeddingSetting, LlmSetting, Project, ProjectLayout
from core.service.process.genai.generator_builder import (
    api_key_name,
    build_embedding_generator,
    build_text_generator,
)
from core.service.process.genai.llm_role import LlmRole


class _Schema(BaseModel):
    name: str
    value: float


class _Calls(list):
    """送ったリクエストの記録。replyがサーバーの返す本文。"""

    reply = " answer "
    finish_reason = "stop"


@pytest.fixture
def posted(monkeypatch):
    calls = _Calls()

    def fake_post(url, headers, json, timeout):
        calls.append(SimpleNamespace(url=url, headers=headers, json=json))
        body = {
            "choices": [
                {
                    "message": {"content": calls.reply, "reasoning_content": "think"},
                    "finish_reason": calls.finish_reason,
                }
            ],
            "usage": {"completion_tokens": 20000},
        }
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: body)

    monkeypatch.setattr(openai_compatible_generator.requests, "post", fake_post)
    return calls


def test_url_normalization():
    base = OpenAiCompatibleTextGenerator(api_url="http://localhost:8080/", model_name="m")
    full = OpenAiCompatibleTextGenerator(
        api_url="http://localhost:8080/v1/chat/completions", model_name="m"
    )
    assert base.url == full.url == "http://localhost:8080/v1/chat/completions"
    webui = OpenAiCompatibleTextGenerator(
        api_url="http://localhost:3000", model_name="m", path="/api/chat/completions"
    )
    assert webui.url == "http://localhost:3000/api/chat/completions"


def test_generate(posted):
    gen = OpenAiCompatibleTextGenerator(
        api_url="http://localhost:8080",
        model_name="qwen",
        api_key="1234",
        config=TextConfig(top_k=40),
    )
    history = [
        Message(role="user", text="q1"),
        Message(role="assistant", text="a1"),
        Message(role="user", text="q2"),
    ]
    assert gen.generate(history, system_instruction="be brief") == "answer"

    call = posted[0]
    assert call.headers["Authorization"] == "Bearer 1234"
    assert call.json["messages"] == [
        {"role": "system", "content": "be brief"},
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "q2"},
    ]
    assert (
        call.json["model"] == "qwen"
        and call.json["top_k"] == 40
        and call.json["temperature"] == 0.7
    )
    assert "max_tokens" not in call.json and "response_format" not in call.json


def test_generate_structured(posted):
    posted.reply = '{"name": "hazard_ratio", "value": 1.8}'
    gen = OpenAiCompatibleTextGenerator(api_url="http://localhost:8080", model_name="qwen")
    assert gen.generate_structured("extract", _Schema) == _Schema(name="hazard_ratio", value=1.8)
    response_format = posted[0].json["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["schema"] == _Schema.model_json_schema()
    assert "Authorization" not in posted[0].headers  # キーが無ければ認証なし

    posted.reply, posted.finish_reason = '{"name": "hazard', "length"
    with pytest.raises(OutputTruncatedError, match="20000トークン、うち思考5字"):
        gen.generate_structured("extract", _Schema)


def test_attachments(posted):
    gen = OpenAiCompatibleTextGenerator(api_url="http://localhost:8080", model_name="qwen")
    gen.generate(
        "describe",
        attachments=[
            Attachment(data=b"\x89PNG", mime_type="image/png"),
            Attachment(data="本文".encode(), mime_type="text/plain"),
        ],
    )
    content = posted[0].json["messages"][0]["content"]
    assert content[0]["image_url"]["url"].startswith("data:image/png;base64,")
    assert content[1] == {"type": "text", "text": "本文"}
    assert content[2] == {"type": "text", "text": "describe"}

    with pytest.raises(ValueError):
        gen.generate("x", attachments=[Attachment(data=b"%PDF", mime_type="application/pdf")])


def test_unsupported_options(posted):
    for config in (TextConfig(thinking_level=ThinkingLevel.LOW), TextConfig(use_url_context=True)):
        gen = OpenAiCompatibleTextGenerator(
            api_url="http://localhost:8080", model_name="qwen", config=config
        )
        with pytest.raises(ValueError):
            gen.generate("x")
    assert posted == []


def _project(client, api_url=None):
    project = Project("id", "TEST_IMPLEMENT__genai", "", "", ProjectLayout("/tmp/TEST_PROJECT_00"))
    project.creative_llm = LlmSetting(client=client, model="qwen", api_url=api_url)
    return project


def _build_creative(project):
    return build_text_generator(project, LlmRole.CREATIVE)


def test_api_key_name():
    assert api_key_name("Gemini") == "AIDC_GEMINI_API_KEY"
    assert api_key_name("Gemini", "http://ignored") == "AIDC_GEMINI_API_KEY"  # URLを持たない提供元
    for url in (
        "http://localhost:8080",
        "http://127.0.0.1:8080/v1/chat/completions",
        "0.0.0.0:8080",
    ):
        assert api_key_name("LlamaCpp", url) == "AIDC_LLAMACPP_LOCALHOST_8080_API_KEY"
    assert api_key_name("LlamaCpp", "https://llama.at-hyogo.xyz/v1/chat/completions") == (
        "AIDC_LLAMACPP_LLAMA_AT_HYOGO_XYZ_API_KEY"
    )
    assert (
        api_key_name("OpenWebUI", "http://localhost:3000")
        == "AIDC_OPENWEBUI_LOCALHOST_3000_API_KEY"
    )


def test_factory(monkeypatch):
    with pytest.raises(ValueError):
        _build_creative(_project("LlamaCpp"))  # api_urlが無い

    # llama.cpp: キーは任意。接続先ごとの名前で保存したキーを使う
    gen = _build_creative(_project("LlamaCpp", "http://localhost:8080"))
    assert isinstance(gen, OpenAiCompatibleTextGenerator) and "Authorization" not in gen.headers
    assert gen.url == "http://localhost:8080/v1/chat/completions"
    secret_env_store.save_secret("AIDC_LLAMACPP_LOCALHOST_8080_API_KEY", "1234")
    secret_env_store.save_secret("AIDC_LLAMACPP_LLAMA_EXAMPLE_API_KEY", "remote-key")
    assert (
        _build_creative(_project("LlamaCpp", "http://localhost:8080")).headers["Authorization"]
        == "Bearer 1234"
    )
    remote = _build_creative(_project("LlamaCpp", "https://llama.example"))
    assert (
        remote.headers["Authorization"] == "Bearer remote-key"
    )  # 同じ種類の別のサーバーは別のキー

    # Ollama: キーは使わない
    gen = _build_creative(_project("Ollama", "http://localhost:11434"))
    assert (
        gen.url == "http://localhost:11434/v1/chat/completions"
        and "Authorization" not in gen.headers
    )

    # Open WebUI: パスが違い、キーは必須。シェルの環境変数は読まない
    monkeypatch.setenv("OPEN_WEBUI_API_KEY", "from-shell")
    with pytest.raises(ValueError, match="AIDC_OPENWEBUI_LOCALHOST_3000_API_KEY"):
        _build_creative(_project("OpenWebUI", "http://localhost:3000"))
    secret_env_store.save_secret("AIDC_OPENWEBUI_LOCALHOST_3000_API_KEY", "sk-test")
    gen = _build_creative(_project("OpenWebUI", "http://localhost:3000"))
    assert gen.url == "http://localhost:3000/api/chat/completions"
    assert gen.headers["Authorization"] == "Bearer sk-test"


def test_build_embedding_generator():
    project = _project("LlamaCpp", "http://localhost:8080")
    with pytest.raises(ValueError, match="Embedding"):
        build_embedding_generator(project)  # 設定が無い
    project.embedding = EmbeddingSetting(
        client="LlamaCpp", model="bge-m3", api_url="http://localhost:8080"
    )
    secret_env_store.save_secret(
        "AIDC_LLAMACPP_LOCALHOST_8080_API_KEY", "1234"
    )  # 文章生成と同じ接続先なら同じキー
    gen = build_embedding_generator(project)
    assert isinstance(gen, OpenAiCompatibleEmbeddingGenerator) and gen.model_name == "bge-m3"
    assert (
        gen.url == "http://localhost:8080/v1/embeddings"
        and gen.headers["Authorization"] == "Bearer 1234"
    )
