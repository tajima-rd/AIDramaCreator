# core/service/api/preference.py
"""
プロジェクトの設定(Project > Preferences)の公開API。現状は生成AIの設定(project.yamlのgenai
セクション=文章生成・音声合成・埋め込み)と、その入力補助(モデル名の一覧・接続先URLの候補・APIキーの状態と保存)。

APIキーの値は返さない(名前と伏せ字だけ)。キーはプロジェクトの外(~/.aidc/secrets.env)に、
提供元と接続先から決まる名前で保存し、全プロジェクトで共有するため、モデル名の一覧・URLの
候補・キーの状態と保存はプロジェクトを指定しない。
"""

from typing import Optional, Union

from core.genai.factory import (
    EMBEDDING_CLIENTS,
    SPEECH_CLIENTS,
    TEXT_CLIENTS,
    api_key_required,
    requires_api_url,
)
from core.infra.store import project_registry_store
from core.infra.store.project_file_store import read_project
from core.project.project import EmbeddingSetting, LlmSetting, Project, TtsSetting
from core.schema import (
    ApiKeyInfo,
    ApiKeyUpdateRequest,
    ApiUrlCandidateInfo,
    ApiUrlCandidateListResult,
    EmbeddingConnectionTestRequest,
    EmbeddingConnectionTestResult,
    GenaiClientInfo,
    GenaiSettingInfo,
    LlmConnectionTestRequest,
    LlmConnectionTestResult,
    ModelListRequest,
    ModelListResult,
    PreferenceInfo,
    PreferenceUpdateRequest,
)
from core.service.process.edit import preference_editor
from core.service.process.genai import genai_setting_inspector
from core.service.process.genai.embedding_connection_tester import check_embedding_connection
from core.service.process.genai.llm_connection_tester import check_llm_connection

# ModelListRequest.kind → 設定の型
SETTING_TYPES = {"llm": LlmSetting, "tts": TtsSetting, "embedding": EmbeddingSetting}


def _client_info(name: str) -> GenaiClientInfo:
    return GenaiClientInfo(name=name, requires_api_url=requires_api_url(name), api_key_required=api_key_required(name))


def _setting_info(setting: Optional[Union[LlmSetting, TtsSetting, EmbeddingSetting]]) -> Optional[GenaiSettingInfo]:
    if setting is None:
        return None
    return GenaiSettingInfo(client=setting.client, model=setting.model, api_url=setting.api_url)


def _to_info(project: Project) -> PreferenceInfo:
    return PreferenceInfo(
        llm=_setting_info(project.llm),
        tts=_setting_info(project.tts),
        embedding=_setting_info(project.embedding),
        llm_clients=[_client_info(c) for c in TEXT_CLIENTS],
        tts_clients=[_client_info(c) for c in SPEECH_CLIENTS],
        embedding_clients=[_client_info(c) for c in EMBEDDING_CLIENTS],
    )


def get_preferences(project_id: str) -> PreferenceInfo:
    layout = project_registry_store.resolve_layout(project_id)
    return _to_info(read_project(layout.root_dir))


def update_preferences(project_id: str, request: PreferenceUpdateRequest) -> PreferenceInfo:
    layout = project_registry_store.resolve_layout(project_id)
    llm = LlmSetting(**request.llm.model_dump()) if request.llm else None
    tts = TtsSetting(**request.tts.model_dump()) if request.tts else None
    embedding = EmbeddingSetting(**request.embedding.model_dump()) if request.embedding else None
    return _to_info(preference_editor.update_genai_settings(layout, llm, tts, embedding))


def test_llm_connection(project_id: str, request: LlmConnectionTestRequest) -> LlmConnectionTestResult:
    """保存前の設定で、実際に短い文章を生成できるかを試す。失敗は例外ではなくok=Falseで返す。"""
    layout = project_registry_store.resolve_layout(project_id)
    project = read_project(layout.root_dir)
    setting = preference_editor.normalize_llm_setting(LlmSetting(**request.llm.model_dump()))
    outcome = check_llm_connection(project, setting)
    return LlmConnectionTestResult(
        ok=outcome.ok,
        message=outcome.message,
        response_text=outcome.response_text,
        elapsed_seconds=outcome.elapsed_seconds,
    )


def test_embedding_connection(project_id: str, request: EmbeddingConnectionTestRequest) -> EmbeddingConnectionTestResult:
    """保存前の設定で、実際に短い文章を埋め込めるかを試す。失敗は例外ではなくok=Falseで返す。"""
    layout = project_registry_store.resolve_layout(project_id)
    project = read_project(layout.root_dir)
    setting = preference_editor.normalize_embedding_setting(EmbeddingSetting(**request.embedding.model_dump()))
    outcome = check_embedding_connection(project, setting)
    return EmbeddingConnectionTestResult(
        ok=outcome.ok,
        message=outcome.message,
        dimensions=outcome.dimensions,
        elapsed_seconds=outcome.elapsed_seconds,
    )


def list_models(request: ModelListRequest) -> ModelListResult:
    """保存前の設定で使えるモデル名の一覧。接続できない・キーが無い等は例外(呼び出し側が理由を見せる)。"""
    cls = SETTING_TYPES[request.kind]
    api_url = (request.setting.api_url or "").strip() or None
    setting = cls(client=request.setting.client, model=request.setting.model, api_url=api_url)
    return ModelListResult(models=genai_setting_inspector.available_models(request.kind, setting))


def list_api_url_candidates(client: str) -> ApiUrlCandidateListResult:
    """OpenAI互換のサーバーの接続先の候補(応答するものが先)。"""
    return ApiUrlCandidateListResult(
        candidates=[
            ApiUrlCandidateInfo(url=c.url, source=c.source, reachable=c.reachable)
            for c in genai_setting_inspector.url_candidates(client)
        ]
    )


def _key_info(client: str, api_url: Optional[str]) -> ApiKeyInfo:
    state = genai_setting_inspector.api_key_state(client, (api_url or "").strip() or None)
    return ApiKeyInfo(name=state.name, required=state.required, available=state.available, masked=state.masked)


def get_api_key(client: str, api_url: Optional[str] = None) -> ApiKeyInfo:
    """提供元と接続先で決まるAPIキーの名前と状態。"""
    return _key_info(client, api_url)


def update_api_key(request: ApiKeyUpdateRequest) -> ApiKeyInfo:
    """APIキーを保存する(~/.aidc/secrets.env)。名前は提供元と接続先から決まる。"""
    preference_editor.save_api_key(request.client, request.api_url, request.value)
    return _key_info(request.client, request.api_url)
