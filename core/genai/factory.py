# core/genai/factory.py
"""
提供元の名前・モデル・接続先・APIキーの値から、生成器(TextGenerator/SpeechGenerator の具象)を
組み立てる。設定の入力補助(使えるモデル名の一覧・接続先URLの候補)もここから提供元ごとの具象へ
振り分ける。

- 提供元(client)ごとの違いはここに集める。OpenAI互換のサーバー(LlamaCpp・Ollama・OpenWebUI)は
  同じ具象(openai_compatible/)を使い、エンドポイントのパス・APIキーの扱い・既定のURLだけが違う
  (OPENAI_COMPATIBLE_SERVERS)
- APIキーは値として受け取るだけで、どこに保存するか・どこから読むかは使う側が決める
  (このパッケージは他のプロジェクトでも使えるよう、使う側のコードに依存しない)
- 提供元の具象は任意の依存を必要とすることがあるため、使うときに初めてimportする
"""

import os
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlsplit

from .generator import (
    EmbeddingConfig,
    EmbeddingGenerator,
    SpeechConfig,
    SpeechGenerator,
    TextConfig,
    TextGenerator,
)

# 提供元(client) → APIキーが必須か。キーを使わないことが多い提供元(手元のサーバー)は任意
API_KEY_REQUIRED = {
    "Gemini": True,
    "LlamaCpp": False,
    "Ollama": False,
    "OpenWebUI": True,
}


@dataclass(frozen=True)
class OpenAiCompatibleServer:
    """OpenAI互換のサーバーの種類ごとの違い。api_urlにはサーバーのURLだけを書けばよい。"""

    chat_path: str  # chat/completions
    models_path: str  # モデル一覧
    health_path: str  # 応答の確認(URLの自動検出)
    default_url: str  # 手元で動かす場合の既定のURL
    url_env: Optional[str] = None  # 接続先のURLを持つ環境変数(あれば候補にする)
    embeddings_path: Optional[str] = None  # 埋め込み(embeddings)。Noneなら埋め込みには使わない


OPENAI_COMPATIBLE_SERVERS = {
    "LlamaCpp": OpenAiCompatibleServer(
        "/v1/chat/completions", "/v1/models", "/health", "http://localhost:8080", "LLAMA_API_URL", "/v1/embeddings"
    ),
    # OLLAMA_HOSTはOllama自身が使う環境変数("127.0.0.1:11434"のようにスキームを省くことが多い)
    "Ollama": OpenAiCompatibleServer(
        "/v1/chat/completions", "/v1/models", "/api/version", "http://localhost:11434", "OLLAMA_HOST", "/v1/embeddings"
    ),
    # Open WebUIの埋め込みのエンドポイントは未確認のため、埋め込みには使わない
    "OpenWebUI": OpenAiCompatibleServer(
        "/api/chat/completions", "/api/models", "/health", "http://localhost:3000", "OPEN_WEBUI_URL"
    ),
}


# 選べる提供元(clientの値)
TEXT_CLIENTS = ("Gemini", *OPENAI_COMPATIBLE_SERVERS)
SPEECH_CLIENTS = ("Gemini",)
EMBEDDING_CLIENTS = ("Gemini", *(name for name, s in OPENAI_COMPATIBLE_SERVERS.items() if s.embeddings_path))


def requires_api_url(client: str) -> bool:
    """接続先のURL(api_url)が必須の提供元か(OpenAI互換のサーバー)。"""
    return client in OPENAI_COMPATIBLE_SERVERS


def api_key_required(client: str) -> bool:
    return API_KEY_REQUIRED.get(client, False)


def _checked_api_key(client: str, api_key: Optional[str]) -> Optional[str]:
    if not api_key and api_key_required(client):
        raise ValueError(f"{client}にはAPIキーが必要です。")
    return api_key or None


def _checked_api_url(client: str, api_url: Optional[str]) -> str:
    if not api_url:
        raise ValueError(f"{client}にはサーバーのURL(api_url)が必要です。")
    return api_url


def create_text_generator(
    client: str,
    model: str,
    *,
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
    config: Optional[TextConfig] = None,
) -> TextGenerator:
    """提供元(client)・モデル・接続先・APIキーから文章生成器を作る。"""
    if client == "Gemini":
        api_key = _checked_api_key(client, api_key)  # google-genaiをimportする前に確かめる
        from .gemini import GeminiTextGenerator

        return GeminiTextGenerator(api_key=api_key, model_name=model, config=config)
    if client in OPENAI_COMPATIBLE_SERVERS:
        from .openai_compatible import OpenAiCompatibleTextGenerator

        return OpenAiCompatibleTextGenerator(
            api_url=_checked_api_url(client, api_url),
            model_name=model,
            api_key=_checked_api_key(client, api_key),
            config=config,
            path=OPENAI_COMPATIBLE_SERVERS[client].chat_path,
        )
    raise ValueError(f"未対応のLLMクライアントです: {client}")


def create_speech_generator(
    client: str,
    model: str,
    *,
    api_key: Optional[str] = None,
    config: Optional[SpeechConfig] = None,
) -> SpeechGenerator:
    """提供元(client)・モデル・APIキーから音声合成器を作る。"""
    if client == "Gemini":
        api_key = _checked_api_key(client, api_key)  # google-genaiをimportする前に確かめる
        from .gemini import GeminiSpeechGenerator

        return GeminiSpeechGenerator(api_key=api_key, model_name=model, config=config)
    raise ValueError(f"未対応のTTSクライアントです: {client}")


def create_embedding_generator(
    client: str,
    model: str,
    *,
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
    config: Optional[EmbeddingConfig] = None,
) -> EmbeddingGenerator:
    """提供元(client)・モデル・接続先・APIキーから埋め込みの生成器を作る。"""
    if client == "Gemini":
        api_key = _checked_api_key(client, api_key)  # google-genaiをimportする前に確かめる
        from .gemini import GeminiEmbeddingGenerator

        return GeminiEmbeddingGenerator(api_key=api_key, model_name=model, config=config)
    if client in EMBEDDING_CLIENTS:
        from .openai_compatible import OpenAiCompatibleEmbeddingGenerator
        from .openai_compatible.server_inspector import server_base_url

        server = OPENAI_COMPATIBLE_SERVERS[client]
        return OpenAiCompatibleEmbeddingGenerator(
            api_url=server_base_url(_checked_api_url(client, api_url), server.chat_path),
            model_name=model,
            api_key=_checked_api_key(client, api_key),
            config=config,
            path=server.embeddings_path,
        )
    raise ValueError(f"未対応の埋め込みのクライアントです: {client}")


# ---------------------------------------------------------------------------
# 設定の入力補助
# ---------------------------------------------------------------------------


def list_models(kind: str, client: str, *, api_url: Optional[str] = None, api_key: Optional[str] = None) -> list[str]:
    """その提供元・接続先・APIキーで使えるモデル名の一覧。kindは"llm"・"tts"・"embedding"。

    接続できない・キーが無い等はそのまま例外(呼び出し側が理由を利用者に見せる)。
    """
    clients = {"llm": TEXT_CLIENTS, "tts": SPEECH_CLIENTS, "embedding": EMBEDDING_CLIENTS}.get(kind)
    if clients is None:
        raise ValueError(f"未対応の用途です: {kind}")
    if client not in clients:
        raise ValueError(f"未対応の提供元です: {client}")
    if client == "Gemini":
        from .gemini.model_lister import list_models as list_gemini_models

        return list_gemini_models(_checked_api_key(client, api_key), kind)

    from .openai_compatible.server_inspector import list_models as list_server_models
    from .openai_compatible.server_inspector import server_base_url

    server = OPENAI_COMPATIBLE_SERVERS[client]
    if not api_url:
        raise ValueError(f"{client}のモデル一覧を得るには、サーバーのURL(API URL)が必要です。")
    return list_server_models(
        server_base_url(api_url, server.chat_path), server.models_path, _checked_api_key(client, api_key), kind
    )


@dataclass(frozen=True)
class ApiUrlCandidate:
    url: str
    source: str  # 候補の出どころ(環境変数名か"default")
    reachable: bool


def _normalize_server_url(value: str, server: OpenAiCompatibleServer) -> str:
    """環境変数の値("127.0.0.1:11434"・"0.0.0.0"・"https://host/v1/chat/completions"等)をサーバーのURLにする。"""
    from .openai_compatible.server_inspector import server_base_url

    value = value.strip()
    if "://" not in value:
        value = "http://" + value
    parts = urlsplit(value)
    host = parts.hostname or "localhost"
    if host in ("0.0.0.0", "::"):
        host = "localhost"  # 待ち受けの指定で、接続先としては手元
    port = parts.port or (urlsplit(server.default_url).port if parts.scheme == "http" and not parts.path.strip("/") else None)
    netloc = f"{host}:{port}" if port else host
    return server_base_url(f"{parts.scheme}://{netloc}{parts.path}", server.chat_path)


def api_url_candidates(client: str) -> list[ApiUrlCandidate]:
    """OpenAI互換のサーバーの接続先の候補(環境変数・手元の既定のURL)と、それぞれが応答するか。

    応答する候補を先に並べる。OpenAI互換でない提供元(Gemini)は空。
    """
    server = OPENAI_COMPATIBLE_SERVERS.get(client)
    if server is None:
        return []
    from .openai_compatible.server_inspector import is_reachable

    sources: dict[str, str] = {}
    if server.url_env and os.getenv(server.url_env):
        sources[_normalize_server_url(os.environ[server.url_env], server)] = server.url_env
    sources.setdefault(server.default_url, "default")
    candidates = [ApiUrlCandidate(url, source, is_reachable(url, server.health_path)) for url, source in sources.items()]
    return sorted(candidates, key=lambda c: not c.reachable)
