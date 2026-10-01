# core/schema/api/preference.py
"""プロジェクトの設定(Project > Preferences)。現状は生成AIの設定のみ。"""

from typing import Literal, Optional

from pydantic import BaseModel


class GenaiSettingInfo(BaseModel):
    """生成AIの接続先(project.yamlのgenai.llm/tts/embedding)。APIキーは持たない。"""

    client: str
    model: str
    api_url: Optional[str] = None


class GenaiClientInfo(BaseModel):
    """選べる提供元と、その既定。"""

    name: str
    requires_api_url: bool
    api_key_required: bool


class PreferenceInfo(BaseModel):
    llm: Optional[GenaiSettingInfo] = None
    tts: Optional[GenaiSettingInfo] = None
    embedding: Optional[GenaiSettingInfo] = None  # 資料の検索の埋め込み(未設定なら語による検索だけ)
    llm_clients: list[GenaiClientInfo]
    tts_clients: list[GenaiClientInfo]
    embedding_clients: list[GenaiClientInfo]


class PreferenceUpdateRequest(BaseModel):
    """設定を置き換える。Noneはその設定を消す。"""

    llm: Optional[GenaiSettingInfo] = None
    tts: Optional[GenaiSettingInfo] = None
    embedding: Optional[GenaiSettingInfo] = None


class LlmConnectionTestRequest(BaseModel):
    """保存前の設定で試せるよう、試す設定そのものを渡す。"""

    llm: GenaiSettingInfo


class LlmConnectionTestResult(BaseModel):
    ok: bool
    message: str
    response_text: Optional[str] = None
    elapsed_seconds: float


class EmbeddingConnectionTestRequest(BaseModel):
    """保存前の設定で試せるよう、試す設定そのものを渡す。"""

    embedding: GenaiSettingInfo


class EmbeddingConnectionTestResult(BaseModel):
    ok: bool
    message: str
    dimensions: Optional[int] = None  # 返ったベクトルの長さ
    elapsed_seconds: float


class ModelListRequest(BaseModel):
    """保存前の設定(提供元・接続先・APIキーの環境変数)で、使えるモデル名を問い合わせる。modelは空でよい。"""

    kind: Literal["llm", "tts", "embedding"]
    setting: GenaiSettingInfo


class ModelListResult(BaseModel):
    models: list[str]


class ApiUrlCandidateInfo(BaseModel):
    url: str
    source: str  # 候補の出どころ(環境変数名か"default")
    reachable: bool


class ApiUrlCandidateListResult(BaseModel):
    candidates: list[ApiUrlCandidateInfo]


class ApiKeyInfo(BaseModel):
    """提供元と接続先で決まるAPIキーの状態(~/.aidc/secrets.env)。値そのものは返さない。"""

    name: str  # 例: AIDC_GEMINI_API_KEY、AIDC_LLAMACPP_LOCALHOST_8080_API_KEY
    required: bool
    available: bool
    masked: Optional[str] = None  # 先頭と末尾の4文字だけ


class ApiKeyUpdateRequest(BaseModel):
    """APIキーを保存する(~/.aidc/secrets.env)。名前は提供元と接続先からサーバーが決める。"""

    client: str
    api_url: Optional[str] = None
    value: str
