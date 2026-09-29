# core/genai/openai_compatible/server_inspector.py
"""
OpenAI互換のサーバーへの問い合わせ(設定の入力補助): 使えるモデル名の一覧と、
サーバーが応答するかどうか。エンドポイントのパスはサーバーの種類ごとに違うため、呼び出し側
(genai.factory)が渡す。
"""

import requests

# 埋め込み(embedding)専用のモデルは文章生成に使えないため、選択肢から除く(名前の一部)
EMBEDDING_MODEL_MARKERS = ("embed",)
INSPECT_TIMEOUT_SECONDS = 5


def server_base_url(api_url: str, chat_path: str) -> str:
    """設定のapi_url(サーバーのURLか、chat/completionsまで含むURL)から、サーバーのURLを得る。"""
    api_url = api_url.rstrip("/")
    for suffix in (chat_path, "/v1/chat/completions", "/chat/completions"):
        if api_url.endswith(suffix):
            return api_url[: -len(suffix)]
    return api_url


def list_models(base_url: str, models_path: str, api_key: str | None = None, kind: str = "llm") -> list[str]:
    """サーバーのモデル一覧(OpenAI形式の{"data": [{"id": ...}]})からモデル名を名前順に返す。

    kindが"embedding"なら全てを返す(埋め込みのモデルは名前で見分けられるとは限らないため)。
    それ以外は埋め込み専用と分かるものを除く。
    """
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    response = requests.get(base_url.rstrip("/") + models_path, headers=headers, timeout=INSPECT_TIMEOUT_SECONDS)
    response.raise_for_status()
    ids = [m.get("id") for m in response.json().get("data", []) if m.get("id")]
    if kind == "embedding":
        return sorted(ids)
    return sorted(i for i in ids if not any(marker in i.lower() for marker in EMBEDDING_MODEL_MARKERS))


def is_reachable(base_url: str, health_path: str, timeout: float = 2.0) -> bool:
    """サーバーが応答するか(認証が要るサーバーの401等も「応答した」とみなす)。"""
    try:
        response = requests.get(base_url.rstrip("/") + health_path, timeout=timeout)
    except requests.RequestException:
        return False
    return response.status_code < 500
