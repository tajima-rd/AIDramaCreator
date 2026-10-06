# core/schema/api/scene_translation.py
"""
シーンの台詞の翻訳(core.service.api.scene_translation。Dramaturgy EditorのScenesタブのTranslation)のDTO。
訳文は返すだけで、下書きは変えない(画面で確かめて直してから、下書きの直接編集で保存する)。
"""

from pydantic import BaseModel


class SceneTranslationRequest(BaseModel):
    dramaturgy_id: str
    scene_id: str


class SceneTranslationLine(BaseModel):
    line_id: str
    number: int  # 台詞の番号(1から)
    translated_text: str  # 訳文(訳が無ければ空文字)


class SceneTranslationResult(BaseModel):
    language: str  # 訳した言語(作品のoutput_language)
    lines: list[SceneTranslationLine]
    warnings: list[str] = []
