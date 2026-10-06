# core/prompt/recording.py
"""
音声の生成(Dramaturgy EditorのRecordingタブ)で、演出付きの台詞(Dialogue)1つを音声合成に渡す指示。
旧来の音声の生成(core/prompt/drama_production/sound.py)と同じ構成(AUDIO PROFILE・THE SCENE・DIRECTOR'S NOTES・TRANSCRIPT)で、
作品のモデル(配役の演じ方・訛り、シーンの場所と状況、台詞の演出)から作る。生成AIは呼ばない。
"""

from typing import Optional

from core.genai.prompt import BulletInstruction, Prompt, Section, TextBlock
from core.model.drama import Cast, Scene
from core.model.drama.script_element import Dialogue


def _scene_title(scene: Scene, dialogue: Dialogue) -> str:
    """場面(台詞が状況を持てばその状況、無ければシーンの状況)の見出し。"""
    situation = dialogue.situation or scene.situation
    location = situation.location or scene.location
    facts = [location.name if location else None, situation.time_of_day, situation.environment]
    return " / ".join(f for f in facts if f) or (scene.title or "")


def speech_prompt(scene: Scene, cast: Cast, dialogue: Dialogue, text: str) -> Prompt:
    """台詞1つの音声合成の指示。textは読み上げる文(音声にする文か訳文。感情タグを含む)。"""
    performance = cast.performance
    direction = dialogue.direction
    situation = dialogue.situation or scene.situation

    profile: list = []
    if performance.title:
        profile.append(Section(title=f'"{performance.title}"', children=[TextBlock(performance.description)] if performance.description else []))
    elif performance.description:
        profile.append(TextBlock(performance.description))

    scene_children = [TextBlock(t) for t in (situation.description, dialogue.action) if t]

    style_items = [
        item
        for item in (
            direction.style,
            f"Dynamics: {direction.dynamics}" if direction.dynamics else None,
            f"Emotion: {direction.emotion}" if direction.emotion else None,
        )
        if item
    ]
    pace: Optional[str] = direction.pace or performance.pace
    notes: list = []
    if style_items:
        notes.append(Section(title="Style", children=[BulletInstruction(items=style_items)]))
    if pace:
        notes.append(TextBlock(f"Pace: {pace}"))
    if cast.accent:
        notes.append(TextBlock(f"Accent: {cast.accent}"))
    notes.append(Section(title="TRANSCRIPT", children=[TextBlock(text)]))

    return Prompt(
        components=[
            Section(title=f"AUDIO PROFILE: {cast.character.name}", children=profile),
            Section(title=f"THE SCENE: {_scene_title(scene, dialogue)}", children=scene_children),
            Section(title="DIRECTOR'S NOTES", children=notes),
        ]
    )
