# core/project/project.py
"""
プロジェクト(ディレクトリ単位のコンテナ)の定義。UML上の集約の根(Project ◇— Dataset)。

- Project: project.yamlに対応する、プロジェクトそのもの(ID・名前・日時等)
- LlmSetting/TtsSetting/EmbeddingSetting: プロジェクトが使う生成AI(文章生成・音声合成・資料の検索の埋め込み)の接続先。
  文章生成は、作品作り用(creative_llm)と作業補助用(assistive_llm)の2つを持つ(タスクごとの使い分けは
  core.service.process.genai.llm_role)。APIキー等の秘密情報はproject.yamlに持たない(~/.aidc/secrets.env、
  core.service.process.genai.generator_builder)
- ProjectLayout: プロジェクトのディレクトリ内の、構成要素の所在の定義。ファイル配置は
  アプリ内部の固定値で、project.yamlのpathsセクションはそのミラーにすぎない

所在の解決にproject.yamlを読む必要は無い(レジストリが持つディレクトリから決まる)ため、
ProjectLayoutをProjectから分けて定義する。

QIDMから持ち込んだ暫定の形(docs/future_design.md「Projectの作り直し」)。現行の制作の流れ(main.py)は
まだ使わない(<root_dir>/model/のモデル定義YAMLを、core/service/process/production/_model_definition_project.pyで読む)。
"""

import os
from dataclasses import dataclass
from typing import Optional

PROJECT_YAML_FILENAME = "project.yaml"
# プロジェクトのSQLite(暫定。現状はDatasetの台帳だけを持つ。docs/future_design.md「SQLite」)
PROJECT_DB_FILENAME = "project.db"
DATASETS_DIRNAME = "datasets"
DRAFTS_DIRNAME = "drafts"
# プロジェクトのユーザー既定(エージェント等。core.infra.store.agent_default_store)
USER_DEFAULT_DIRNAME = "user_default"
# 生成した音声(Dramaturgy EditorのRecordingタブ)の置き場所
RECORDINGS_DIRNAME = "recordings"

PROTOCOL_VERSION = "0.1.0"
DEFAULT_SERVER_BASE_URL = "http://127.0.0.1:8100"


class ProjectNotFoundError(LookupError):
    """指定したproject_idがレジストリに登録されていない。"""


@dataclass(frozen=True)
class ProjectLayout:
    """プロジェクトのディレクトリ内の、構成要素の所在。"""

    root_dir: str

    @property
    def project_yaml_path(self) -> str:
        return os.path.join(self.root_dir, PROJECT_YAML_FILENAME)

    @property
    def project_db_path(self) -> str:
        return os.path.join(self.root_dir, PROJECT_DB_FILENAME)

    @property
    def datasets_dir(self) -> str:
        return os.path.join(self.root_dir, DATASETS_DIRNAME)

    @property
    def drafts_dir(self) -> str:
        """作成途中の下書きの置き場所(対話方式の制作で使う予定。docs/future_design.md)。"""
        return os.path.join(self.root_dir, DRAFTS_DIRNAME)

    @property
    def recordings_dir(self) -> str:
        """生成した音声の置き場所(<作品のid>/<言語>/<シーンのid>.mp3)。"""
        return os.path.join(self.root_dir, RECORDINGS_DIRNAME)

    @property
    def user_default_agents_dir(self) -> str:
        """エージェントのユーザー既定(職能ごとのYAML)の置き場所。"""
        return os.path.join(self.root_dir, USER_DEFAULT_DIRNAME, "agents")


@dataclass
class LlmSetting:
    """文章生成に使う生成AIの接続先。clientはcore.genai.factoryが対応する名前
    (Gemini/LlamaCpp/Ollama/OpenWebUI)。

    api_urlは手元のLLMサーバー等、接続先のURLを持つクライアントのためのもの(OpenAI互換の
    サーバーでは必須、Geminiでは不要)。APIキーはここにもproject.yamlにも持たない(キーの名前は
    提供元と接続先から決まり、値は~/.aidc/secrets.envにある。core.service.process.genai.generator_builder.api_key_name)。
    """

    client: str
    model: str
    api_url: Optional[str] = None


@dataclass
class TtsSetting:
    """音声合成に使う生成AIの接続先。clientはcore.genai.factoryが対応する名前(現状Geminiのみ)。

    api_urlの意味はLlmSettingと同じ。
    """

    client: str
    model: str
    api_url: Optional[str] = None


@dataclass
class EmbeddingSetting:
    """資料の検索(core.genai.rag)の埋め込みに使う生成AIの接続先。clientはcore.genai.factoryが
    対応する名前(Gemini/LlamaCpp/Ollama)。未設定なら資料の検索は語による検索(BM25)だけで行う。

    api_urlの意味はLlmSettingと同じ。
    """

    client: str
    model: str
    api_url: Optional[str] = None


@dataclass
class Project:
    """project.yamlに対応する、プロジェクトそのもの。"""

    project_id: str
    name: str
    created_at: str
    modified_at: str
    layout: ProjectLayout
    server_base_url: str = DEFAULT_SERVER_BASE_URL
    protocol_version: str = PROTOCOL_VERSION
    creative_llm: Optional[LlmSetting] = None  # 作品作り(品質が要るタスク)の文章生成
    assistive_llm: Optional[LlmSetting] = None  # 作業補助(課金の無い生成AIで足りるタスク)の文章生成
    tts: Optional[TtsSetting] = None
    embedding: Optional[EmbeddingSetting] = None
