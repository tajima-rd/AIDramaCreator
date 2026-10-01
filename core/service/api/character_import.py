# core/service/api/character_import.py
"""
企画書の登場人物の取り込みの公開API(人物パネルのCharactersタブ。docs/architecture.md 9節)。下書き(draft_id)に対して行い、
取り込みの結果は生成AIの提案として下書きに反映する(確定はSave Version)。生成AIは作業補助(assistive_llm)を使う。

エラーは例外で返す: project_idが未登録ならProjectNotFoundError、下書きが無ければDraftNotFoundError、作品・登場人物が無い・
名前が無い・登録の有無とmodeが合わない・作業補助の生成AIが未設定ならValueError。生成AIの呼び出しの失敗はその例外のまま。
"""

from core.infra.store.project_file_store import read_project
from core.infra.store.project_registry_store import resolve_layout
from core.schema import (
    CharacterConflictCheckRequest,
    CharacterConflictCheckResult,
    CharacterImportRequest,
    CharacterImportResult,
)
from core.service.process.genai import character_importer


def check_conflict(project_id: str, draft_id: str, request: CharacterConflictCheckRequest) -> CharacterConflictCheckResult:
    """登録済みの人物と、企画書の登場人物の説明の矛盾を確かめる(下書きは変えない)。"""
    layout = resolve_layout(project_id)
    outcome = character_importer.check_conflict(
        read_project(layout.root_dir), layout.project_db_path, draft_id, request.dramaturgy_id, request.name
    )
    return CharacterConflictCheckResult(character_id=outcome.character_id, conflict=outcome.conflict, reasons=outcome.reasons)


def import_character(project_id: str, draft_id: str, request: CharacterImportRequest) -> CharacterImportResult:
    """企画書の登場人物を取り込み、下書きに反映する。"""
    layout = resolve_layout(project_id)
    outcome = character_importer.import_character(
        read_project(layout.root_dir),
        layout.project_db_path,
        draft_id,
        request.dramaturgy_id,
        request.name,
        character_importer.ImportMode(request.mode),
    )
    return CharacterImportResult(revision=outcome.revision, character_id=outcome.character_id)
