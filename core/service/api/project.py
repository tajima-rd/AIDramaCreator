# core/service/api/project.py
"""
プロジェクト(Project/Connectionメニュー)の公開API。

エラーは例外で返す: project_idが未登録ならProjectNotFoundError、project.yamlが
無ければFileNotFoundError、作成先・複製先が空でないディレクトリならFileExistsError、
指定パスのproject.yamlが別のproject_idを持つならValueError。
"""

import os
import shutil

from core.infra.store import project_registry_store
from core.infra.store.project_file_store import read_project, write_project
from core.model.identifier import new_id
from core.project.project import Project, ProjectNotFoundError
from core.schema import (
    ProjectCreateRequest,
    ProjectInfo,
    ProjectListResult,
    ProjectOpenRequest,
    ProjectPropertiesUpdateRequest,
    ProjectSaveAsRequest,
    ProjectUpdatePathRequest,
)
from core.service.process.edit import project_editor


def _to_info(project: Project) -> ProjectInfo:
    return ProjectInfo(
        protocol_version=project.protocol_version,
        project_id=project.project_id,
        name=project.name,
        created_at=project.created_at,
        modified_at=project.modified_at,
        server_base_url=project.server_base_url,
        path=project.layout.root_dir,
    )


def create_project(request: ProjectCreateRequest) -> ProjectInfo:
    project = project_editor.create_project_files(request.path, request.name)
    project_registry_store.register_project(project.project_id, request.path)
    return _to_info(project)


def open_project(request: ProjectOpenRequest) -> ProjectInfo:
    project = read_project(request.path)
    project_registry_store.register_project(project.project_id, request.path)
    return _to_info(project)


def list_projects() -> ProjectListResult:
    """登録済みのプロジェクトのうち、実体(project.yaml)が見つかるものだけを返す。"""
    infos = []
    for project_id in project_registry_store.list_registered_project_ids():
        try:
            layout = project_registry_store.resolve_layout(project_id)
            infos.append(_to_info(read_project(layout.root_dir)))
        except (ProjectNotFoundError, FileNotFoundError):
            continue
    return ProjectListResult(projects=infos)


def get_project(project_id: str) -> ProjectInfo:
    return _to_info(read_project(project_registry_store.resolve_layout(project_id).root_dir))


def update_project_properties(project_id: str, request: ProjectPropertiesUpdateRequest) -> ProjectInfo:
    layout = project_registry_store.resolve_layout(project_id)
    return _to_info(project_editor.update_properties(layout, request.name, request.server_base_url))


def update_project_path(project_id: str, request: ProjectUpdatePathRequest) -> ProjectInfo:
    """プロジェクトのディレクトリが移動された場合に、レジストリ上の所在を付け替える。"""
    project_registry_store.resolve_layout(project_id)
    project = read_project(request.path)
    if project.project_id != project_id:
        raise ValueError("指定されたパスのproject.yamlは別のproject_idを持っています")
    project_registry_store.update_project_path(project_id, request.path)
    return _to_info(project)


def save_project(project_id: str) -> ProjectInfo:
    return _to_info(project_editor.touch_modified(project_registry_store.resolve_layout(project_id)))


def save_project_as(project_id: str, request: ProjectSaveAsRequest) -> ProjectInfo:
    """プロジェクトのディレクトリを丸ごと複製し、新しいproject_idで登録する。"""
    layout = project_registry_store.resolve_layout(project_id)
    if os.path.exists(request.path) and (not os.path.isdir(request.path) or os.listdir(request.path)):
        raise FileExistsError(f"既に存在し、空のディレクトリではありません: {request.path}")
    # 空の既存ディレクトリも複製先として許可する(copytreeは既定で既存ディレクトリを拒否する)。
    shutil.copytree(layout.root_dir, request.path, dirs_exist_ok=True)

    new_project = read_project(request.path)
    new_project.project_id = new_id()
    if request.name:
        new_project.name = request.name
    write_project(new_project)
    project_registry_store.register_project(new_project.project_id, request.path)
    return _to_info(new_project)
