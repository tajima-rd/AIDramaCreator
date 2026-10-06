# core/service/process/production/scene_recorder.py
"""
シーンの音声の生成(Dramaturgy EditorのRecordingタブ。docs/architecture.md 8節)。

演出付きの原稿(Scene.elementsのDialogue)を台詞の順に、演者(Actor)の声で1つずつ音声合成し、台詞の後の間(pause_after)を
挟んでつなぎ、シーンごとに1つのmp3にする(連結と書き出しにpydub・ffmpeg)。読み上げる文は、言語で決まる:
制作の言語(input_language)なら音声にする文(text)、音声の言語(output_language。制作の言語と違うとき)なら訳文(translated_text)。

足りないもの(台詞が無い・演出付きの原稿の無い台詞・原稿が今の台詞と食い違う台詞・その言語の文の無い台詞・声の決まっていない配役)
があるシーンは断る
(課金の無駄を防ぐ。scene_problemsで先に一覧にする)。演者の音声合成の提供元・モデルが空なら、project.yamlのgenai.tts。
"""

import io
from typing import Optional

from pydub import AudioSegment

from core.model.agent import Actor
from core.model.drama import Cast, Dramaturgy, Scene
from core.model.drama.script_element import Dialogue
from core.project.project import Project
from core.prompt.ai_build.direction import bare_text
from core.prompt.recording import speech_prompt
from core.service.process.genai.generator_builder import build_actor_speech_generator

TEXT = "text"
TRANSLATED_TEXT = "translated_text"

# 台詞の後の間(Directionの工程の決まり。抽象的な言葉を、音声をつなぐときだけ長さにする)。無ければShort
PAUSES_MS = {"short": 300, "medium": 700, "long": 1500}
DEFAULT_PAUSE_MS = PAUSES_MS["short"]


class RecordingLanguage:
    """生成できる言語。sourceは読み上げる原稿の項目(TEXT=音声にする文、TRANSLATED_TEXT=訳文)。"""

    def __init__(self, code: str, source: str):
        self.code: str = code
        self.source: str = source


def recording_languages(dramaturgy: Dramaturgy) -> list[RecordingLanguage]:
    """作品で生成できる言語(制作の言語と、それと違う音声の言語)。どちらも無ければ空。"""
    languages = []
    if dramaturgy.input_language:
        languages.append(RecordingLanguage(dramaturgy.input_language, TEXT))
    output = dramaturgy.output_language
    if output and output != dramaturgy.input_language:
        # 制作の言語が無ければ、音声にする文がその言語の文
        languages.append(RecordingLanguage(output, TRANSLATED_TEXT if dramaturgy.input_language else TEXT))
    return languages


def find_language(dramaturgy: Dramaturgy, code: str) -> RecordingLanguage:
    languages = recording_languages(dramaturgy)
    if not languages:
        raise ValueError("作品の言語(Input Language・Output Language)を、Propertiesタブで設定してください。")
    language = next((lang for lang in languages if lang.code == code), None)
    if language is None:
        raise ValueError(f"言語「{code}」の音声は作れません(作れるのは {', '.join(lang.code for lang in languages)})。")
    return language


class _Take:
    """台詞1つの読み上げに要るもの。"""

    def __init__(self, dialogue: Dialogue, cast: Cast, actor: Actor, text: str):
        self.dialogue: Dialogue = dialogue
        self.cast: Cast = cast
        self.actor: Actor = actor
        self.text: str = text


def _takes(dramaturgy: Dramaturgy, scene: Scene, language: RecordingLanguage) -> tuple[list[_Take], list[str]]:
    """シーンの台詞の順の読み上げと、足りないもの。"""
    problems: list[str] = []
    lines = sorted(scene.script.lines, key=lambda line: line.order)
    if not lines:
        return [], ["台詞がありません(Build with AIのScriptの工程で書けます)。"]
    dialogues = {e.line_id: e for e in scene.elements if isinstance(e, Dialogue)}
    casts = {c.id: c for c in dramaturgy.casts}
    actors = {a.casting_id: a for a in dramaturgy.agents if isinstance(a, Actor)}
    takes: list[_Take] = []
    no_voice: list[str] = []
    for number, line in enumerate(lines, start=1):
        dialogue = dialogues.get(line.id)
        if dialogue is None:
            problems.append(f"台詞{number}に演出付きの原稿がありません(Build with AIのDirectionの工程で作れます)。")
            continue
        if bare_text(dialogue.text) != bare_text(line.text):
            # 原稿を作った後に台詞の文言を変えた(Scenesタブ)。原稿・訳文は古い台詞のもの
            problems.append(
                f"台詞{number}の原稿が、今の台詞と食い違います(Build with AIのDirectionか、ScenesタブのScriptで直せます)。"
            )
        text = (getattr(dialogue, language.source) or "").strip()
        if not text:
            what = "訳文" if language.source == TRANSLATED_TEXT else "音声にする文"
            problems.append(f"台詞{number}に{language.code}の{what}がありません。")
        cast = casts.get(dialogue.cast_id) or line.cast
        actor = actors.get(cast.id)
        if actor is None or not actor.voice_name:
            if cast.character.name not in no_voice:
                no_voice.append(cast.character.name)
            continue
        takes.append(_Take(dialogue, cast, actor, text))
    problems += [f"「{name}」の声が決まっていません(Build with AIのAudition・Castsタブで選べます)。" for name in no_voice]
    return takes, problems


def scene_problems(dramaturgy: Dramaturgy, scene: Scene, language: RecordingLanguage) -> list[str]:
    """シーンの音声を作るのに足りないもの(無ければ空)。"""
    return _takes(dramaturgy, scene, language)[1]


def _pause(dialogue: Dialogue) -> AudioSegment:
    value: Optional[str] = (dialogue.direction.pause_after or "").strip().lower()
    return AudioSegment.silent(duration=PAUSES_MS.get(value, DEFAULT_PAUSE_MS))


def record_scene(project: Project, dramaturgy: Dramaturgy, scene: Scene, language: RecordingLanguage) -> bytes:
    """シーンの音声(mp3のバイト列)を作る。足りないものがあればValueError(音声合成は呼ばない)。"""
    takes, problems = _takes(dramaturgy, scene, language)
    if problems:
        raise ValueError("このシーンの音声は作れません:\n" + "\n".join(f"* {p}" for p in problems))
    generators = {}
    audio = AudioSegment.empty()
    for take in takes:
        key = (take.actor.tts_provider, take.actor.tts_model)
        if key not in generators:
            generators[key] = build_actor_speech_generator(project, *key)
        prompt = speech_prompt(scene, take.cast, take.dialogue, take.text)
        wav = generators[key].synthesize(prompt.to_text(), voice=take.actor.voice_name)
        audio += AudioSegment.from_wav(io.BytesIO(wav)) + _pause(take.dialogue)
    out = io.BytesIO()
    audio.export(out, format="mp3")
    return out.getvalue()
