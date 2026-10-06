# core/service/api/scene_translation.py
"""
シーンの台詞の翻訳の公開API(Dramaturgy EditorのScenesタブのTranslation)。訳文を返すだけで、下書きは変えない。

エラーは例外で返す: project_idが未登録ならProjectNotFoundError、下書きが無ければDraftNotFoundError、作品・シーンの誤り・言語の誤り
(制作の言語が無い・制作の言語と同じ)・台詞の無いシーン・生成AIの未設定はValueError。生成AIの呼び出しの失敗はその例外のまま。
"""

from core.infra.store.project_file_store import read_project
from core.infra.store.project_registry_store import resolve_layout
from core.schema.api.scene_translation import (
    SceneTranslationLine,
    SceneTranslationRequest,
    SceneTranslationResult,
)
from core.service.process.genai import scene_translator


def translate_scene(project_id: str, draft_id: str, request: SceneTranslationRequest) -> SceneTranslationResult:
    project = read_project(resolve_layout(project_id).root_dir)
    outcome = scene_translator.translate_scene(
        project, draft_id, request.dramaturgy_id, request.scene_id, request.language
    )
    return SceneTranslationResult(
        language=outcome.language,
        lines=[
            SceneTranslationLine(line_id=line.line_id, number=line.number, translated_text=line.translated_text)
            for line in outcome.lines
        ],
        warnings=outcome.warnings,
    )
