# core/service/process/edit/preference_editor.py
"""
プロジェクトの設定(Preferences)の更新。現状は生成AIの設定(project.yamlのgenaiセクション=
Project.llm/Project.tts/Project.embedding)のみ。

project.yamlにはAPIキーを書かない(docs/architecture.md「生成AI(`core/genai`)の設定はProjectに
持たせる」)。キーはsave_api_keyで、プロジェクトの外(~/.aidc/secrets.env)に、提供元と接続先から
決まる名前で保存する。
"""

from datetime import UTC, datetime
from typing import Optional, Union

from core.genai.factory import EMBEDDING_CLIENTS, SPEECH_CLIENTS, TEXT_CLIENTS, requires_api_url
from core.infra.store import secret_env_store
from core.infra.store.project_file_store import read_project, write_project
from core.project.project import EmbeddingSetting, LlmSetting, Project, ProjectLayout, TtsSetting
from core.service.process.genai.generator_builder import api_key_name


def _blank_to_none(value: Optional[str]) -> Optional[str]:
    value = value.strip() if value else ""
    return value or None


def validate_genai_setting(setting: Union[LlmSetting, TtsSetting, EmbeddingSetting], clients: tuple[str, ...], label: str) -> None:
    """提供元・モデル・接続先URLの整合を確かめる。合わなければValueError。"""
    if setting.client not in clients:
        raise ValueError(f"{label}: 未対応の提供元です: {setting.client}(選べるもの: {', '.join(clients)})")
    if not setting.model:
        raise ValueError(f"{label}: モデルを入力してください。")
    if requires_api_url(setting.client) and not setting.api_url:
        raise ValueError(f"{label}: {setting.client}にはサーバーのURL(API URL)が必要です。")


def normalize_llm_setting(setting: Optional[LlmSetting]) -> Optional[LlmSetting]:
    if setting is None:
        return None
    normalized = LlmSetting(
        client=setting.client.strip(),
        model=setting.model.strip(),
        api_url=_blank_to_none(setting.api_url),
    )
    validate_genai_setting(normalized, TEXT_CLIENTS, "LLM")
    return normalized


def normalize_tts_setting(setting: Optional[TtsSetting]) -> Optional[TtsSetting]:
    if setting is None:
        return None
    normalized = TtsSetting(
        client=setting.client.strip(),
        model=setting.model.strip(),
        api_url=_blank_to_none(setting.api_url),
    )
    validate_genai_setting(normalized, SPEECH_CLIENTS, "TTS")
    return normalized


def normalize_embedding_setting(setting: Optional[EmbeddingSetting]) -> Optional[EmbeddingSetting]:
    if setting is None:
        return None
    normalized = EmbeddingSetting(
        client=setting.client.strip(),
        model=setting.model.strip(),
        api_url=_blank_to_none(setting.api_url),
    )
    validate_genai_setting(normalized, EMBEDDING_CLIENTS, "Embedding")
    return normalized


def update_genai_settings(
    layout: ProjectLayout,
    llm: Optional[LlmSetting],
    tts: Optional[TtsSetting],
    embedding: Optional[EmbeddingSetting] = None,
) -> Project:
    """生成AIの設定を置き換える(Noneはその設定を消す)。検証してからproject.yamlに書く。"""
    llm = normalize_llm_setting(llm)
    tts = normalize_tts_setting(tts)
    embedding = normalize_embedding_setting(embedding)
    project = read_project(layout.root_dir)
    project.llm = llm
    project.tts = tts
    project.embedding = embedding
    project.modified_at = datetime.now(UTC).astimezone().isoformat()
    write_project(project)
    return project


def save_api_key(client: str, api_url: Optional[str], value: str) -> str:
    """APIキーを保存する(~/.aidc/secrets.env)。名前は提供元と接続先から決まる。保存した名前を返す。"""
    client = client.strip()
    if client not in (*TEXT_CLIENTS, *SPEECH_CLIENTS, *EMBEDDING_CLIENTS):
        raise ValueError(f"未対応の提供元です: {client}")
    api_url = _blank_to_none(api_url)
    if requires_api_url(client) and not api_url:
        raise ValueError(f"{client}のAPIキーは接続先ごとに保存するため、API URLを先に入力してください。")
    name = api_key_name(client, api_url)
    secret_env_store.save_secret(name, value)
    return name
