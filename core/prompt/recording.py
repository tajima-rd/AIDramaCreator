# core/prompt/recording.py
"""
音声の生成(Dramaturgy EditorのRecordingタブ)で、演出付きの台詞(Dialogue)1つを音声合成に渡す指示。
旧来の音声の生成(core/prompt/drama_production/sound.py)と同じ構成(AUDIO PROFILE・THE SCENE・DIRECTOR'S NOTES・TRANSCRIPT)。
生成AIは呼ばない。

- 見出しに番号を付けない素のMarkdownにし、「TRANSCRIPTだけを、その言語で読む」と明記する。
- **利用者が書いた設定(人物の名前・演じ方・話す速さ・訛り・場所・状況)は渡さない**(どの言語でも)。渡すと、音声合成がそれを
  読み上げたり、それを元に台本に無い台詞を作って話したりした(2026-10-06の実験。日本語専用の声に日本語の設定と英語の台本を渡すと
  設定を読んで台本を日本語に訳し戻し、日本語の台本でも設定から作った前置きを話した。渡さなければ台本どおりに読んだ。docs/known_issues.md)。
  渡すのは、Directionの工程の英語の演出(話し方・速さ・強弱・感情)とト書き、声の性別だけ。
"""

from core.model.drama import Cast
from core.model.drama.script_element import Dialogue

VOICE_GENDERS = {"male": "male", "female": "female", "neutral": "gender-neutral"}


def speech_prompt(cast: Cast, dialogue: Dialogue, text: str, language: str) -> str:
    """台詞1つの音声合成の指示。textは読み上げる文(音声にする文か訳文。感情タグを含む)。languageは読む言語の名前
    (例: 한국어 (ko))。"""
    direction = dialogue.direction
    gender = VOICE_GENDERS.get(cast.voice_gender.value) if cast.voice_gender else None
    parts = ["# AUDIO PROFILE", f"A {gender} voice." if gender else "A natural speaking voice."]
    if dialogue.action:
        parts += ["", "# THE SCENE", dialogue.action]
    notes = [
        f"Style: {direction.style}" if direction.style else None,
        f"Dynamics: {direction.dynamics}" if direction.dynamics else None,
        f"Emotion: {direction.emotion}" if direction.emotion else None,
        f"Pace: {direction.pace}" if direction.pace else None,
        f"Language: {language}. Read ONLY the text under TRANSCRIPT aloud, exactly as written, in this language. "
        "Do not read these notes or the headings.",
    ]
    parts += ["", "# DIRECTOR'S NOTES", *[n for n in notes if n]]
    parts += ["", "# TRANSCRIPT", text]
    return "\n".join(parts)
