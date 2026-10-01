# core/service/process/genai/generator_builder.py
"""
プロジェクトの生成AIの設定(project.yamlのgenaiセクション=Project.llm/tts/embedding)と保存済みの
APIキーから、生成器を作る。core.genaiは他のプロジェクトでも使えるようAIDCを知らないため、
AIDCの設定・キーの置き場所との橋渡しはここで行う。

- APIキーはproject.yamlにもシェルの環境変数にも持たず、Project > Preferencesで入力して
  ~/.aidc/secrets.envに保存したものだけを使う(core.infra.store.secret_env_store)。キーの名前は
  提供元と接続先からシステムが決める(api_key_name。例: AIDC_GEMINI_API_KEY、
  AIDC_LLAMACPP_LOCALHOST_8080_API_KEY)ため、同じ種類のサーバーを複数使い分けられる
"""

import re
from typing import Optional
from urllib.parse import urlsplit

from core.genai import (
    EmbeddingConfig,
    EmbeddingGenerator,
    SpeechConfig,
    SpeechGenerator,
    TextConfig,
    TextGenerator,
)
from core.genai.factory import (
    api_key_required,
    create_embedding_generator,
    create_speech_generator,
    create_text_generator,
    requires_api_url,
)
from core.infra.store import secret_env_store
from core.project.project import EmbeddingSetting, LlmSetting, Project, TtsSetting

GenaiSetting = LlmSetting | TtsSetting | EmbeddingSetting

# APIキーの名前で、手元を指すホスト名を1つにそろえる
LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1", "0.0.0.0")


def api_key_name(client: str, api_url: Optional[str] = None) -> str:
    """提供元と接続先から決まるAPIキーの名前(~/.aidc/secrets.envでの名前)。

    接続先のURLを持つ提供元はホスト(手元はLOCALHOST)と、URLに明記されたポートを含める
    (例: AIDC_LLAMACPP_LOCALHOST_8080_API_KEY)。パス・スキームは含めない。
    """
    parts = ["AIDC", client]
    if requires_api_url(client) and api_url and api_url.strip():
        url = api_url.strip()
        split = urlsplit(url if "://" in url else "http://" + url)
        host = split.hostname or ""
        parts.append("localhost" if host in LOCAL_HOSTS else host)
        if split.port:
            parts.append(str(split.port))
    parts.append("API_KEY")
    return re.sub(r"[^A-Z0-9]+", "_", "_".join(parts).upper()).strip("_")


def saved_api_key(setting: GenaiSetting) -> Optional[str]:
    """保存済みのAPIキー(~/.aidc/secrets.env)を得る。必須の提供元で無ければValueError。"""
    name = api_key_name(setting.client, setting.api_url)
    api_key = secret_env_store.get_secret(name)
    if not api_key and api_key_required(setting.client):
        raise ValueError(
            f"{setting.client}のAPIキー({name})が未設定です。Project > Preferencesで入力してください。"
        )
    return api_key


def build_text_generator(project: Project, config: Optional[TextConfig] = None) -> TextGenerator:
    """プロジェクトの設定(Project.llm)から文章生成器を作る。"""
    setting = project.llm
    if setting is None:
        raise ValueError("このプロジェクトには文章生成(LLM)の設定がありません。")
    return create_text_generator(
        setting.client, setting.model, api_url=setting.api_url, api_key=saved_api_key(setting), config=config
    )


def build_speech_generator(project: Project, config: Optional[SpeechConfig] = None) -> SpeechGenerator:
    """プロジェクトの設定(Project.tts)から音声合成器を作る。"""
    setting = project.tts
    if setting is None:
        raise ValueError("このプロジェクトには音声合成(TTS)の設定がありません。")
    return create_speech_generator(setting.client, setting.model, api_key=saved_api_key(setting), config=config)


def build_embedding_generator(project: Project, config: Optional[EmbeddingConfig] = None) -> EmbeddingGenerator:
    """プロジェクトの設定(Project.embedding)から埋め込みの生成器を作る。"""
    setting = project.embedding
    if setting is None:
        raise ValueError("このプロジェクトには埋め込み(Embedding)の設定がありません。")
    return create_embedding_generator(
        setting.client, setting.model, api_url=setting.api_url, api_key=saved_api_key(setting), config=config
    )
