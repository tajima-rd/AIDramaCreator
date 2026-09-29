# core/infra/store/project_registry_store.py
"""
プロジェクトの永続レジストリ(project_id → プロジェクトのルートディレクトリ)の読み書き。

project_idはメモリ上の一時的なセッションではなく、ユーザーのローカル環境
(既定ではホームディレクトリ配下)にあるレジストリファイルへ永続化する。
AIDC_REGISTRY_PATHで保存先を変更できる。

project_idの登録と、project_idからプロジェクトの所在(core.project.project.ProjectLayout)の
解決を行う。テストはREGISTRY_PATHをtmp_path配下へ差し替えて、ユーザーの実レジストリ
に触れないようにする(tests/conftest.py)。
"""

import os

import yaml

from core.project.project import ProjectLayout, ProjectNotFoundError

REGISTRY_PATH = os.environ.get(
    "AIDC_REGISTRY_PATH",
    os.path.join(os.path.expanduser("~"), ".aidc", "projects.yaml"),
)


def load_registry() -> dict:
    if not os.path.exists(REGISTRY_PATH):
        return {}
    with open(REGISTRY_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or {}


def save_registry(registry: dict) -> None:
    os.makedirs(os.path.dirname(REGISTRY_PATH), exist_ok=True)
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(registry, f, allow_unicode=True, sort_keys=False, default_flow_style=False)


def register_project(project_id: str, root_dir: str) -> None:
    registry = load_registry()
    registry[project_id] = {"path": os.path.abspath(root_dir)}
    save_registry(registry)


def update_project_path(project_id: str, root_dir: str) -> None:
    registry = load_registry()
    if project_id not in registry:
        raise ProjectNotFoundError(project_id)
    registry[project_id]["path"] = os.path.abspath(root_dir)
    save_registry(registry)


def resolve_layout(project_id: str) -> ProjectLayout:
    """project_idから、プロジェクトの構成要素の所在を解決する(project.yamlは読まない)。"""
    entry = load_registry().get(project_id)
    if entry is None:
        raise ProjectNotFoundError(project_id)
    return ProjectLayout(root_dir=entry["path"])


def list_registered_project_ids() -> list[str]:
    return list(load_registry().keys())
