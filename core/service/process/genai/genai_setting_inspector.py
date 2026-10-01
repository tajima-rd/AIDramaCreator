# core/service/process/genai/genai_setting_inspector.py
"""
生成AIの設定の入力補助(Project > Preferences): 使えるモデル名の一覧、接続先URLの候補、
APIキーの状態(値そのものは返さず、名前と伏せ字だけ)。
"""

from dataclasses import dataclass
from typing import Optional

from core.genai.factory import (
    ApiUrlCandidate,
    api_key_required,
    api_url_candidates,
    list_models,
)
from core.infra.store import secret_env_store

from .generator_builder import GenaiSetting, api_key_name, saved_api_key


@dataclass(frozen=True)
class ApiKeyState:
    name: str  # ~/.aidc/secrets.envでの名前(提供元と接続先から決まる)
    required: bool
    available: bool
    masked: Optional[str]  # 先頭と末尾の4文字だけ(短いキーは全て伏せる)


def mask_secret(value: str) -> str:
    if len(value) < 12:
        return "*" * 4
    return f"{value[:4]}…{value[-4:]}"


def api_key_state(client: str, api_url: Optional[str]) -> ApiKeyState:
    name = api_key_name(client, api_url)
    value = secret_env_store.get_secret(name)
    return ApiKeyState(
        name=name,
        required=api_key_required(client),
        available=bool(value),
        masked=mask_secret(value) if value else None,
    )


def available_models(kind: str, setting: GenaiSetting) -> list[str]:
    return list_models(kind, setting.client, api_url=setting.api_url, api_key=saved_api_key(setting))


def url_candidates(client: str) -> list[ApiUrlCandidate]:
    return api_url_candidates(client)
