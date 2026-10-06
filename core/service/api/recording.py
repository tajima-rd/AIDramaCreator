# core/service/api/recording.py
"""
音声の生成(Dramaturgy EditorのRecordingタブ)の公開API。原稿は編集用の下書き(draft_id)から読む(画面に出ている内容)。
音声はシーンごとに作り、<プロジェクト>/recordings/<作品のid>/<言語>/<シーンのid>.mp3に置く(生成し直すと上書き)。

エラーは例外で返す: project_idが未登録ならProjectNotFoundError、下書きが無ければDraftNotFoundError、音声が無ければKeyError、
作品・シーン・言語の誤り・足りないもの・音声合成の未設定はValueError。音声合成の呼び出しの失敗はその例外のまま。
"""

from core.infra.io.model_definition_reader import ModelDefinition
from core.infra.store import recording_store
from core.infra.store.project_file_store import read_project
from core.infra.store.project_registry_store import resolve_layout
from core.model.drama import Act, Dramaturgy, Scene
from core.project.project import ProjectLayout
from core.schema.api.recording import (
    RecordingCreateRequest,
    RecordingLanguageInfo,
    RecordingListResult,
    RecordingSceneInfo,
)
from core.service.process.edit import drama_draft_editor
from core.service.process.production import scene_recorder


def _dramaturgy(layout: ProjectLayout, draft_id: str, dramaturgy_id: str) -> Dramaturgy:
    model: ModelDefinition = drama_draft_editor.load_draft_model(layout.project_db_path, draft_id)
    dramaturgy = next((d for d in model.dramaturgies if d.id == dramaturgy_id), None)
    if dramaturgy is None:
        raise ValueError(f"作品が見つかりません: {dramaturgy_id}")
    return dramaturgy


def _scenes(dramaturgy: Dramaturgy) -> list[tuple[int, int, Act, Scene]]:
    """作品のすべてのシーン((幕の番号, シーンの番号, 幕, シーン)。どちらの番号も1から)。"""
    return [
        (act_number, scene_number, act, scene)
        for act_number, act in enumerate(sorted(dramaturgy.acts, key=lambda a: a.order), start=1)
        for scene_number, scene in enumerate(sorted(act.scenes, key=lambda s: s.order), start=1)
    ]


def _scene_info(
    layout: ProjectLayout,
    dramaturgy: Dramaturgy,
    language: scene_recorder.RecordingLanguage,
    act_number: int,
    scene_number: int,
    scene: Scene,
) -> RecordingSceneInfo:
    recording = recording_store.find_recording(layout, dramaturgy.id, language.code, scene.id)
    return RecordingSceneInfo(
        scene_id=scene.id,
        act_number=act_number,
        scene_number=scene_number,
        title=scene.title,
        line_count=len(scene.script.lines),
        problems=scene_recorder.scene_problems(dramaturgy, scene, language),
        notices=scene_recorder.scene_notices(dramaturgy, scene, language),
        recorded=recording is not None,
        recorded_at=recording.recorded_at if recording else None,
        size=recording.size if recording else None,
    )


def list_recordings(project_id: str, draft_id: str, dramaturgy_id: str, language: str = "") -> RecordingListResult:
    """作品で作れる言語と、シーンごとの足りないもの・音声の有無。languageが空なら最初の言語。"""
    layout = resolve_layout(project_id)
    dramaturgy = _dramaturgy(layout, draft_id, dramaturgy_id)
    languages = scene_recorder.recording_languages(dramaturgy)
    infos = [RecordingLanguageInfo(code=lang.code, source=lang.source) for lang in languages]
    if not languages:
        return RecordingListResult(languages=[], language=None, scenes=[])
    selected = scene_recorder.find_language(dramaturgy, language) if language else languages[0]
    return RecordingListResult(
        languages=infos,
        language=selected.code,
        scenes=[
            _scene_info(layout, dramaturgy, selected, act_number, scene_number, scene)
            for act_number, scene_number, _, scene in _scenes(dramaturgy)
        ],
    )


def record_scene(project_id: str, request: RecordingCreateRequest) -> RecordingSceneInfo:
    """シーンの音声を作って保存する(あれば上書き)。足りないものがあれば音声合成を呼ばずにValueError。"""
    layout = resolve_layout(project_id)
    project = read_project(layout.root_dir)
    dramaturgy = _dramaturgy(layout, request.draft_id, request.dramaturgy_id)
    language = scene_recorder.find_language(dramaturgy, request.language)
    entry = next((e for e in _scenes(dramaturgy) if e[3].id == request.scene_id), None)
    if entry is None:
        raise ValueError(f"シーンが見つかりません: {request.scene_id}")
    act_number, scene_number, _, scene = entry
    data = scene_recorder.record_scene(project, dramaturgy, scene, language)
    recording_store.save_recording(layout, dramaturgy.id, language.code, scene.id, data)
    return _scene_info(layout, dramaturgy, language, act_number, scene_number, scene)


def recording_file(project_id: str, dramaturgy_id: str, language: str, scene_id: str) -> str:
    """シーンの音声のファイルのパス(無ければKeyError)。"""
    recording = recording_store.find_recording(resolve_layout(project_id), dramaturgy_id, language, scene_id)
    if recording is None:
        raise KeyError(f"音声がありません: {language}/{scene_id}")
    return recording.path
