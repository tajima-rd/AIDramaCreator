# core/service/process/edit/project_editor.py
"""
プロジェクトの作成と、project.yamlの更新(更新日時・プロパティ)。

プロジェクトのDB(project.db)のスキーマ初期化は、core.infra.storeの各モジュールが
「接続するだけでスキーマ付きの空DBを生成する」設計になっているため、ここでは空DBを作るための
接続を1回行うだけでよい。
project.yamlの読み書きはcore.infra.store.project_file_storeが担う。
"""

import os
from datetime import UTC, datetime

from core.infra.store import agent_default_store, dataset_registry_store
from core.infra.store.project_file_store import read_project, write_project
from core.model.identifier import new_id
from core.project.project import Project, ProjectLayout


def _now() -> str:
    return datetime.now(UTC).astimezone().isoformat()


def create_project_files(root_dir: str, name: str) -> Project:
    """空のディレクトリに、プロジェクトの構成要素(project.yaml・空のDB・datasets/・エージェントのユーザー既定)を作る。"""
    if os.path.exists(root_dir) and (not os.path.isdir(root_dir) or os.listdir(root_dir)):
        raise FileExistsError(f"既に存在し、空のディレクトリではありません: {root_dir}")
    layout = ProjectLayout(root_dir=os.path.abspath(root_dir))
    os.makedirs(layout.root_dir, exist_ok=True)
    os.makedirs(layout.datasets_dir, exist_ok=True)
    agent_default_store.ensure_user_defaults(layout)

    # 接続するだけでスキーマ付きの空DBが生成される(core側の設計)。
    dataset_registry_store.list_dataset_entries(layout.project_db_path)

    now = _now()
    project = Project(
        project_id=new_id(),
        name=name,
        created_at=now,
        modified_at=now,
        layout=layout,
    )
    write_project(project)
    return project


def touch_modified(layout: ProjectLayout) -> Project:
    project = read_project(layout.root_dir)
    project.modified_at = _now()
    write_project(project)
    return project


def update_properties(layout: ProjectLayout, name: str, server_base_url: str) -> Project:
    # protocol_version/pathsはアプリ内部の固定値(core.project.project参照)であり
    # ユーザーが変更できるproject.yamlの項目はname/server_base_urlのみ。
    # server_base_urlは現状どのコードからも読み戻されない記録用フィールド
    # (「このプロジェクトが最後にどのサーバーと紐付いていたか」のメモ)だが、
    # 接続先を偽って記録しないよう、保存前の接続テストはフロント側
    # (project_overview_panel.js)で行う。
    project = read_project(layout.root_dir)
    project.name = name
    project.server_base_url = server_base_url
    project.modified_at = _now()
    write_project(project)
    return project
