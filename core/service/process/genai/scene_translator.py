# core/service/process/genai/scene_translator.py
"""
シーンの台詞の翻訳(Dramaturgy EditorのScenesタブのTranslation。docs/architecture.md 8節)。

作品の制作の言語(input_language)から音声の言語(output_language)へ、シーンの台詞を生成AIで訳す。訳すのは原稿の音声にする文
(感情タグ入り。原稿が無ければ台詞)。担当はStageManager(作品のもの。いなければプロジェクトのユーザー既定)、タスクはtranslate。
訳文は返すだけで、下書きは変えない(利用者が画面で確かめて直してからSaveする)。一覧に無い感情タグは外し、訳の無い台詞・
無い番号は注意にする。
"""

from typing import Optional

from core.genai import Message, TextConfig
from core.model.drama import Dramaturgy, Scene
from core.project.project import Project
from core.prompt import scene_translation as prompts
from core.prompt.ai_build.direction import ordered_lines, remove_unknown_tags, translates
from core.service.process.edit import drama_draft_editor
from core.service.process.genai.ai_builder import role_agent
from core.service.process.genai.generator_builder import build_task_text_generator

MAX_OUTPUT_TOKENS = 8192


class TranslatedLine:
    """台詞1つの訳文(訳が無ければtranslated_textは空文字)。numberは台詞の番号(1から)。"""

    def __init__(self, line_id: str, number: int, translated_text: str):
        self.line_id: str = line_id
        self.number: int = number
        self.translated_text: str = translated_text


class TranslationOutcome:
    def __init__(self, language: str, lines: list[TranslatedLine], warnings: list[str]):
        self.language: str = language
        self.lines: list[TranslatedLine] = lines
        self.warnings: list[str] = warnings


def _scene(dramaturgy: Dramaturgy, scene_id: str) -> tuple[Scene, int]:
    for act in dramaturgy.acts:
        for number, scene in enumerate(sorted(act.scenes, key=lambda s: s.order), start=1):
            if scene.id == scene_id:
                return scene, number
    raise ValueError(f"シーンが見つかりません: {scene_id}")


def translate_scene(project: Project, draft_id: str, dramaturgy_id: str, scene_id: str) -> TranslationOutcome:
    """シーンの台詞を訳す。訳さない作品・台詞の無いシーンはValueError。生成AIの失敗はその例外のまま。"""
    model = drama_draft_editor.load_draft_model(project.layout.project_db_path, draft_id)
    dramaturgy: Optional[Dramaturgy] = next((d for d in model.dramaturgies if d.id == dramaturgy_id), None)
    if dramaturgy is None:
        raise ValueError(f"作品が見つかりません: {dramaturgy_id}")
    if not translates(dramaturgy):
        raise ValueError(
            "訳す作品ではありません。PropertiesタブでInput LanguageとOutput Languageを、違う言語に設定してください。"
        )
    scene, scene_number = _scene(dramaturgy, scene_id)
    lines = ordered_lines(scene)
    if not lines:
        raise ValueError("このシーンには台詞がありません。")

    generator = build_task_text_generator(project, prompts.TASK, TextConfig(max_output_tokens=MAX_OUTPUT_TOKENS))
    reply = generator.generate_structured(
        [Message(role="user", text=prompts.translation_context(dramaturgy, scene, scene_number))],
        prompts.SceneTranslationReply,
        system_instruction=prompts.translation_prompt(role_agent(project, dramaturgy, "stage_manager")),
    )

    warnings = [w for w in reply.warnings if w.strip()]
    texts: dict[int, str] = {}
    for item in reply.translations:
        if not 1 <= item.number <= len(lines):
            warnings.append(f"台詞{item.number}はありません(台詞は{len(lines)}行)。その訳を外しました。")
            continue
        text, unknown = remove_unknown_tags(item.translated_text or "")
        warnings += [f"台詞{item.number}の訳文の感情タグ「{tag}」は使えないので、外しました。" for tag in unknown]
        texts[item.number] = text
    missing = [str(n) for n in range(1, len(lines) + 1) if not texts.get(n)]
    if missing:
        warnings.append(f"台詞{'・'.join(missing)}の訳がありません。")
    return TranslationOutcome(
        dramaturgy.output_language,
        [TranslatedLine(line.id, n, texts.get(n, "")) for n, line in enumerate(lines, start=1)],
        warnings,
    )
