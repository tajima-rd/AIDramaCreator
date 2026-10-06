# core/service/process/genai/generator_builder.py
"""
プロジェクトの生成AIの設定(project.yamlのgenaiセクション=Project.creative_llm/assistive_llm/tts/embedding)と保存済みの
APIキーから、生成器を作る。文章生成は役割(作品作り・作業補助)で設定を選ぶ。タスクから作るときは
build_task_text_generator(役割はcore.service.process.genai.llm_roleの対応表で決まる)。
core.genaiは他のプロジェクトでも使えるようAIDCを知らないため、
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

from .llm_role import LlmRole, llm_role_for_task

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


# 役割 → (Projectの属性, 利用者に見せる名前。Generative AIタブの見出しと揃える)
LLM_ROLE_SETTINGS: dict[LlmRole, tuple[str, str]] = {
    LlmRole.CREATIVE: ("creative_llm", "作品作り(Creative LLM)"),
    LlmRole.ASSISTIVE: ("assistive_llm", "作業補助(Assistive LLM)"),
}


def llm_setting(project: Project, role: LlmRole) -> Optional[LlmSetting]:
    """役割に対応する文章生成の設定(未設定ならNone)。"""
    return getattr(project, LLM_ROLE_SETTINGS[role][0])


def build_text_generator(project: Project, role: LlmRole, config: Optional[TextConfig] = None) -> TextGenerator:
    """プロジェクトの設定(役割に対応するProject.creative_llm/assistive_llm)から文章生成器を作る。
    未設定なら、もう一方の役割で代わりに動かさずValueError(黙って課金のある生成AIを使わないため)。"""
    setting = llm_setting(project, role)
    if setting is None:
        raise ValueError(
            f"このプロジェクトには{LLM_ROLE_SETTINGS[role][1]}の文章生成の設定がありません。"
            "Project > Preferences(Generative AIタブ)で設定してください。"
        )
    return create_text_generator(
        setting.client, setting.model, api_url=setting.api_url, api_key=saved_api_key(setting), config=config
    )


def build_task_text_generator(project: Project, task_code: str, config: Optional[TextConfig] = None) -> TextGenerator:
    """タスク(AgentTask.code)に使う文章生成器を作る。役割はllm_roleの対応表で決まる。"""
    return build_text_generator(project, llm_role_for_task(task_code), config)


def build_speech_generator(project: Project, config: Optional[SpeechConfig] = None) -> SpeechGenerator:
    """プロジェクトの設定(Project.tts)から音声合成器を作る。"""
    setting = project.tts
    if setting is None:
        raise ValueError("このプロジェクトには音声合成(TTS)の設定がありません。")
    return create_speech_generator(setting.client, setting.model, api_key=saved_api_key(setting), config=config)


def build_actor_speech_generator(
    project: Project, client: Optional[str], model: Optional[str], config: Optional[SpeechConfig] = None
) -> SpeechGenerator:
    """演者(Actor)の音声合成器。演者の提供元・モデルが空なら、プロジェクトの設定(Project.tts)のもの。"""
    setting = project.tts
    if not client and not model:
        return build_speech_generator(project, config)
    client = client or (setting.client if setting else None)
    model = model or (setting.model if setting else None)
    if not client or not model:
        raise ValueError("音声合成の提供元・モデルが決まっていません(Project > PreferencesのTTSか、演者の設定)。")
    api_url = setting.api_url if setting and setting.client == client else None
    actor_setting = TtsSetting(client=client, model=model, api_url=api_url)
    return create_speech_generator(client, model, api_key=saved_api_key(actor_setting), config=config)


def build_embedding_generator(project: Project, config: Optional[EmbeddingConfig] = None) -> EmbeddingGenerator:
    """プロジェクトの設定(Project.embedding)から埋め込みの生成器を作る。"""
    setting = project.embedding
    if setting is None:
        raise ValueError("このプロジェクトには埋め込み(Embedding)の設定がありません。")
    return create_embedding_generator(
        setting.client, setting.model, api_url=setting.api_url, api_key=saved_api_key(setting), config=config
    )
