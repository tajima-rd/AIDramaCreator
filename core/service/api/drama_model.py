# core/service/api/drama_model.py
"""
作品モデルの正本と版の公開API(読むだけ。docs/architecture.md 7節)。正本を変えるのは下書きの確定(drama_draft)。

作品の中身は、モデル定義YAMLの形(DramaturgyDefinition。作品はdramaturgiesの一覧)で返す。
エラーは例外で返す: project_idが未登録ならProjectNotFoundError、版が無ければVersionNotFoundError。
"""

from core.infra.io.model_definition_reader import load_documents
from core.infra.io.model_definition_writer import model_definition_to_spec
from core.infra.store.drama_version_store import VersionNotFoundError
from core.infra.store.project_registry_store import resolve_layout
from core.schema import DramaModelVersionListResult, DramaModelVersionSummary
from core.schema.formats.dramaturgy_definition import DramaturgyDefinition
from core.service.process.edit import drama_draft_editor

__all__ = ["VersionNotFoundError", "get_model", "get_version", "list_versions"]


def _db_path(project_id: str) -> str:
    return resolve_layout(project_id).project_db_path


def definition_from_yaml(yaml_text: str) -> DramaturgyDefinition:
    """写し(モデル定義YAMLの文字列)を、DTO(DramaturgyDefinition)にする。"""
    documents = load_documents(yaml_text)
    return DramaturgyDefinition.model_validate(documents[0] if documents else {})


def get_model(project_id: str) -> DramaturgyDefinition:
    """正本(確定した最新の作品モデル全体)。まだ確定が無ければ空。"""
    definition = drama_draft_editor.load_model(_db_path(project_id))
    return DramaturgyDefinition.model_validate(model_definition_to_spec(definition))


def list_versions(project_id: str) -> DramaModelVersionListResult:
    db_path = _db_path(project_id)
    return DramaModelVersionListResult(
        current_version=drama_draft_editor.current_version(db_path),
        versions=[
            DramaModelVersionSummary(
                version=v.version, created_at=v.created_at, draft_id=v.draft_id, note=v.note
            )
            for v in drama_draft_editor.list_versions(db_path)
        ],
    )


def get_version(project_id: str, version: int) -> DramaturgyDefinition:
    """版の写し。"""
    return definition_from_yaml(drama_draft_editor.version_yaml(_db_path(project_id), version))
