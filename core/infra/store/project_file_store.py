# core/infra/store/project_file_store.py
"""
project.yamlの読み書き(Projectの永続化)。

プロジェクトのライフサイクル(作成・プロパティ更新等)はcore.service.process.edit.
project_editorが担い、ここはファイルの読み書きのみ。ファイル配置はcore.project.projectの
ProjectLayoutが定義する。
"""

import os
from dataclasses import asdict, fields
from typing import Optional

import yaml

from core.project.project import (
    DATASETS_DIRNAME,
    DEFAULT_SERVER_BASE_URL,
    DRAFTS_DIRNAME,
    PROJECT_DB_FILENAME,
    PROTOCOL_VERSION,
    EmbeddingSetting,
    LlmSetting,
    Project,
    ProjectLayout,
    TtsSetting,
)


def read_project(root_dir: str) -> Project:
    """root_dirのproject.yamlを読む。存在しなければFileNotFoundError。"""
    layout = ProjectLayout(root_dir=os.path.abspath(root_dir))
    yaml_path = layout.project_yaml_path
    if not os.path.exists(yaml_path):
        raise FileNotFoundError(f"project.yaml が見つかりません: {yaml_path}")
    with open(yaml_path, encoding="utf-8") as f:
        spec = yaml.safe_load(f) or {}

    project = spec.get("project", {})
    server = spec.get("server", {})
    genai = spec.get("genai") or {}
    return Project(
        project_id=project["id"],
        name=project["name"],
        created_at=project["created_at"],
        modified_at=project["modified_at"],
        layout=layout,
        server_base_url=server.get("base_url", DEFAULT_SERVER_BASE_URL),
        protocol_version=spec.get("protocol_version", PROTOCOL_VERSION),
        creative_llm=_setting_from_spec(LlmSetting, genai.get("creative_llm")),
        assistive_llm=_setting_from_spec(LlmSetting, genai.get("assistive_llm")),
        tts=_setting_from_spec(TtsSetting, genai.get("tts")),
        embedding=_setting_from_spec(EmbeddingSetting, genai.get("embedding")),
    )


def _setting_from_spec(cls, spec: Optional[dict]):
    # 知らない項目は無視する(以前のapi_key_env等。APIキーの名前は今は提供元と接続先から決まる)。
    if not spec:
        return None
    known = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in spec.items() if k in known})


def _setting_to_spec(setting) -> dict:
    # 未設定(None)の項目はproject.yamlに書かない。
    return {k: v for k, v in asdict(setting).items() if v is not None}


def write_project(project: Project) -> None:
    # 全セクションをprojectから作り直す(Datasetの帳簿はproject.dbのdataset_registryにあり、
    # project.yamlには持たない)。
    yaml_path = project.layout.project_yaml_path
    spec = {
        "protocol_version": PROTOCOL_VERSION,
        "project": {
            "id": project.project_id,
            "name": project.name,
            "created_at": project.created_at,
            "modified_at": project.modified_at,
        },
        "server": {
            "base_url": project.server_base_url,
        },
        "paths": {
            "project_db": PROJECT_DB_FILENAME,
            "datasets_dir": DATASETS_DIRNAME + "/",
            "drafts_dir": DRAFTS_DIRNAME + "/",
        },
    }
    # 生成AIの設定は、設定されている場合のみ書く(APIキー等の秘密情報は持たない)。
    genai = {}
    if project.creative_llm is not None:
        genai["creative_llm"] = _setting_to_spec(project.creative_llm)
    if project.assistive_llm is not None:
        genai["assistive_llm"] = _setting_to_spec(project.assistive_llm)
    if project.tts is not None:
        genai["tts"] = _setting_to_spec(project.tts)
    if project.embedding is not None:
        genai["embedding"] = _setting_to_spec(project.embedding)
    if genai:
        spec["genai"] = genai
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(spec, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
