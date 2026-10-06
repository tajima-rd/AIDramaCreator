# core/prompt/recording.py
"""
音声の生成(Dramaturgy EditorのRecordingタブ)で、演出付きの台詞(Dialogue)1つを音声合成に渡す指示。
旧来の音声の生成(core/prompt/drama_production/sound.py)と同じ構成(AUDIO PROFILE・THE SCENE・DIRECTOR'S NOTES・TRANSCRIPT)で、
作品のモデル(配役の演じ方・訛り、シーンの場所と状況、台詞の演出)から作る。生成AIは呼ばない。

- 見出しに番号を付けない素のMarkdownにする(core.genai.promptの部品は見出しに番号を付ける)。
- 「TRANSCRIPTだけを、その言語で読む」と明記する。
- **制作の言語以外で読むときは、利用者が制作の言語で書いた設定(人物の名前・演じ方・話す速さ・訛り・場所・状況)を渡さない**。
  日本語専用の声に日本語の設定と英語の台本を渡すと、設定を読み上げ、台本を日本語に訳し戻して読んだため(2026-10-06の実験。
  docs/known_issues.md)。演出(Directionの工程の話し方・速さ・強弱・感情)とト書きは英語なので、どの言語でも渡す。
"""

from typing import Optional

from core.model.drama import Cast, Scene
from core.model.drama.script_element import Dialogue

VOICE_GENDERS = {"male": "male", "female": "female", "neutral": "gender-neutral"}


def _scene_title(scene: Scene, dialogue: Dialogue) -> str:
    """場面(台詞が状況を持てばその状況、無ければシーンの状況)の見出し。"""
    situation = dialogue.situation or scene.situation
    location = situation.location or scene.location
    facts = [location.name if location else None, situation.time_of_day, situation.environment]
    return " / ".join(f for f in facts if f) or (scene.title or "")


def speech_prompt(scene: Scene, cast: Cast, dialogue: Dialogue, text: str, language: str, native: bool) -> str:
    """台詞1つの音声合成の指示。textは読み上げる文(音声にする文か訳文。感情タグを含む)。languageは読む言語の名前
    (例: 한국어 (ko))。nativeは制作の言語で読むか(利用者の書いた設定を渡すか)。"""
    performance = cast.performance
    direction = dialogue.direction
    situation = dialogue.situation or scene.situation
    gender = VOICE_GENDERS.get(cast.voice_gender.value) if cast.voice_gender else None

    parts: list[str] = []
    if native:
        parts.append(f"# AUDIO PROFILE: {cast.character.name}")
        if performance.title:
            parts.append(f'## "{performance.title}"')
        if performance.description:
            parts.append(performance.description)
    else:
        parts.append("# AUDIO PROFILE")
        parts.append(f"A {gender} voice." if gender else "A natural speaking voice.")

    scene_lines = [t for t in ((situation.description if native else None), dialogue.action) if t]
    title = _scene_title(scene, dialogue) if native else ""
    if title or scene_lines:
        parts += ["", f"# THE SCENE{': ' + title if title else ''}", *scene_lines]

    notes = [
        f"Style: {direction.style}" if direction.style else None,
        f"Dynamics: {direction.dynamics}" if direction.dynamics else None,
        f"Emotion: {direction.emotion}" if direction.emotion else None,
    ]
    pace: Optional[str] = direction.pace or (performance.pace if native else None)
    notes.append(f"Pace: {pace}" if pace else None)
    notes.append(f"Accent: {cast.accent}" if native and cast.accent else None)
    notes.append(
        f"Language: {language}. Read ONLY the text under TRANSCRIPT aloud, exactly as written, in this language. "
        "Do not read these notes or the headings."
    )
    parts += ["", "# DIRECTOR'S NOTES", *[n for n in notes if n]]
    parts += ["", "# TRANSCRIPT", text]
    return "\n".join(parts)
