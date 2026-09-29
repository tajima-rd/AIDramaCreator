# core/genai/gemini/model_lister.py
"""
Geminiで使えるモデル名の一覧(設定の入力補助のモデルの選択肢)。

Gemini APIのREST(GET https://generativelanguage.googleapis.com/v1beta/models)を直接使う。
google-genaiのmodels.list()と同じ一覧を返すことを確認済み(2026-09-28)で、google-genaiが
入っていない環境でも一覧を出せ、キーの誤り等のエラーが短い文で返る。キーはURLの?key=ではなく
ヘッダー(x-goog-api-key)で渡す(URLに入れるとログ・履歴に残るため)。

supportedGenerationMethodsにgenerateContentを含むものを、用途(文章生成/音声合成)で振り分ける。
埋め込みはembedContentを含むもの。
振り分けは名前による目安で、一覧に無いモデル名も設定できる(GUIで手入力できる)。
"""

import requests

MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"
REQUEST_TIMEOUT_SECONDS = 10

# 文章生成の選択肢から除く、文章生成以外の専用モデル(名前の一部)
NON_TEXT_MODEL_MARKERS = (
    "tts",
    "image",
    "banana",
    "lyria",
    "transcribe",
    "computer-use",
    "robotics",
    "antigravity",
    "deep-research",
)


def fetch_models(api_key: str) -> list[dict]:
    """REST APIのモデル一覧(ページを辿って全件)。キーの誤り等はValueError(APIのメッセージ付き)。"""
    models: list[dict] = []
    page_token = None
    while True:
        params = {"pageSize": 1000}
        if page_token:
            params["pageToken"] = page_token
        response = requests.get(
            MODELS_URL, headers={"x-goog-api-key": api_key}, params=params, timeout=REQUEST_TIMEOUT_SECONDS
        )
        body = response.json() if response.content else {}
        if not response.ok:
            message = (body.get("error") or {}).get("message") or response.reason
            raise ValueError(f"Gemini API ({response.status_code}): {message}")
        models += body.get("models", [])
        page_token = body.get("nextPageToken")
        if not page_token:
            return models


def list_models(api_key: str, kind: str) -> list[str]:
    """kindは"llm"(文章生成)・"tts"(音声合成)・"embedding"(埋め込み)。モデル名(models/は除く)を名前順に返す。"""
    names = []
    for model in fetch_models(api_key):
        if kind == "embedding":
            if "embedContent" in model.get("supportedGenerationMethods", []):
                names.append(model["name"].removeprefix("models/"))
            continue
        if "generateContent" not in model.get("supportedGenerationMethods", []):
            continue
        name = model["name"].removeprefix("models/")
        is_tts = "tts" in name
        if kind == "tts" and is_tts:
            names.append(name)
        elif kind == "llm" and not any(marker in name for marker in NON_TEXT_MODEL_MARKERS):
            names.append(name)
    return sorted(names)
