# core/service/process/production/scene_recorder.py
"""
シーンの音声の生成(Dramaturgy EditorのRecordingタブ。docs/architecture.md 8節)。

演出付きの原稿(Scene.elementsのDialogue)を台詞の順に、演者(Actor)の声で1つずつ音声合成し、台詞の後の間(pause_after)を
挟んでつなぎ、シーンごとに1つのmp3にする(連結と書き出しにpydub・ffmpeg)。読み上げる文は、言語で決まる:
制作の言語(input_language)なら音声にする文(text)、ほかの言語ならその言語の訳文(Dialogue.translations)。作れる言語は、制作の言語・
既定の音声の言語(output_language)・作品のどこかの台詞に訳文のある言語(言語の一覧の順。2026-10-06ユーザー)。

足りないもの(台詞が無い・演出付きの原稿の無い台詞・原稿が今の台詞と食い違う台詞・その言語の文の無い台詞・声の決まっていない配役)
があるシーンは断る
(課金の無駄を防ぐ。scene_problemsで先に一覧にする)。声は、演者に読む言語の声(Actor.voices)があればそれ、無ければ既定の声。提供元・モデルが空なら、演者の既定、それも空ならproject.yamlのgenai.tts。
制作の言語以外で読むときは、利用者が制作の言語で書いた設定を音声合成に渡さない(core.prompt.recording)。
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
from core.infra.io.language_list_reader import read_languages
from core.service.process.genai.generator_builder import build_actor_speech_generator

TEXT = "text"
TRANSLATION = "translation"

# 台詞の後の間(Directionの工程の決まり。抽象的な言葉を、音声をつなぐときだけ長さにする)。無ければShort
PAUSES_MS = {"short": 300, "medium": 700, "long": 1500}
DEFAULT_PAUSE_MS = PAUSES_MS["short"]


class RecordingLanguage:
    """生成できる言語。sourceは読み上げる原稿の項目(TEXT=音声にする文、TRANSLATION=その言語の訳文)。"""

    def __init__(self, code: str, source: str):
        self.code: str = code
        self.source: str = source


def translation_text(dialogue: Dialogue, language: str) -> str:
    """台詞のその言語の訳文(無ければ空文字)。"""
    return next((t.text for t in dialogue.translations if t.language == language), "")


def language_name(code: str) -> str:
    """音声合成への指示に書く言語の名前(その言語での名前とコード。一覧に無ければコード)。"""
    entry = next((e for e in read_languages() if e.code == code), None)
    return f"{entry.name} ({code})" if entry else code


def recording_languages(dramaturgy: Dramaturgy) -> list[RecordingLanguage]:
    """作品で生成できる言語: 制作の言語・既定の音声の言語・訳文のある言語。訳文のある言語は言語の一覧の順に並べ、
    一覧に無いものは後ろ。どれも無ければ空。制作の言語が無ければ、音声にする文を既定の音声の言語の文とする。"""
    languages = []
    seen = set()

    def add(code: Optional[str], source: str) -> None:
        if code and code not in seen:
            seen.add(code)
            languages.append(RecordingLanguage(code, source))

    add(dramaturgy.input_language, TEXT)
    add(dramaturgy.output_language, TRANSLATION if dramaturgy.input_language else TEXT)
    translated = {
        t.language
        for act in dramaturgy.acts
        for scene in act.scenes
        for e in scene.elements
        if isinstance(e, Dialogue)
        for t in e.translations
    }
    rank = {entry.code: i for i, entry in enumerate(read_languages())}
    for code in sorted(translated, key=lambda c: (rank.get(c, len(rank)), c)):
        add(code, TRANSLATION)
    return languages


def find_language(dramaturgy: Dramaturgy, code: str) -> RecordingLanguage:
    languages = recording_languages(dramaturgy)
    if not languages:
        raise ValueError("作品の言語(Input Language・Output Language)を、Propertiesタブで設定してください。")
    language = next((lang for lang in languages if lang.code == code), None)
    if language is None:
        raise ValueError(f"言語「{code}」の音声は作れません(作れるのは {', '.join(lang.code for lang in languages)})。")
    return language


class VoiceChoice:
    """ある言語を読むときの演者の声。language_voiceは言語ごとの声を使うか(Falseなら既定の声)。"""

    def __init__(self, voice_name: str, tts_provider: Optional[str], tts_model: Optional[str], language_voice: bool):
        self.voice_name: str = voice_name
        self.tts_provider: Optional[str] = tts_provider
        self.tts_model: Optional[str] = tts_model
        self.language_voice: bool = language_voice


def voice_for(actor: Actor, language: str) -> Optional[VoiceChoice]:
    """演者がlanguageを読む声: その言語の声があればそれ(提供元・モデルが空なら演者の既定)、無ければ既定の声。どちらも無ければNone。"""
    voice = next((v for v in actor.voices if v.language == language), None)
    if voice is not None:
        return VoiceChoice(
            voice.voice_name, voice.tts_provider or actor.tts_provider, voice.tts_model or actor.tts_model, True
        )
    if actor.voice_name:
        return VoiceChoice(actor.voice_name, actor.tts_provider, actor.tts_model, False)
    return None


class _Take:
    """台詞1つの読み上げに要るもの。"""

    def __init__(self, dialogue: Dialogue, cast: Cast, voice: VoiceChoice, text: str):
        self.dialogue: Dialogue = dialogue
        self.cast: Cast = cast
        self.voice: VoiceChoice = voice
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
        text = (dialogue.text if language.source == TEXT else translation_text(dialogue, language.code)).strip()
        if not text:
            what = "訳文" if language.source == TRANSLATION else "音声にする文"
            problems.append(f"台詞{number}に{language.code}の{what}がありません。")
        cast = casts.get(dialogue.cast_id) or line.cast
        actor = actors.get(cast.id)
        voice = voice_for(actor, language.code) if actor is not None else None
        if voice is None:
            if cast.character.name not in no_voice:
                no_voice.append(cast.character.name)
            continue
        takes.append(_Take(dialogue, cast, voice, text))
    problems += [f"「{name}」の声が決まっていません(Build with AIのAudition・Castsタブで選べます)。" for name in no_voice]
    return takes, problems


def scene_notices(dramaturgy: Dramaturgy, scene: Scene, language: RecordingLanguage) -> list[str]:
    """音声は作れるが確かめるとよいこと: 既定の声の言語(配役の言語、無ければ作品の言語)と違う言語を、その言語の声が無いので
    既定の声で読む演者(既定の声はその言語をうまく読めないことがある。docs/known_issues.md)。"""
    notices: list[str] = []
    for take in _takes(dramaturgy, scene, language)[0]:
        default_language = take.cast.language or dramaturgy.output_language or dramaturgy.input_language
        if take.voice.language_voice or not default_language or default_language == language.code:
            continue
        notice = (
            f"「{take.cast.character.name}」には{language.code}の声が無いので、既定の声({take.voice.voice_name})で読みます"
            "(CastsタブのVoices by Languageで選べます)。"
        )
        if notice not in notices:
            notices.append(notice)
    return notices


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
    native = language.source == TEXT  # 制作の言語で読む(利用者の書いた設定も渡す)
    name = language_name(language.code)
    for take in takes:
        key = (take.voice.tts_provider, take.voice.tts_model)
        if key not in generators:
            generators[key] = build_actor_speech_generator(project, *key)
        prompt = speech_prompt(scene, take.cast, take.dialogue, take.text, name, native)
        wav = generators[key].synthesize(prompt, voice=take.voice.voice_name)
        audio += AudioSegment.from_wav(io.BytesIO(wav)) + _pause(take.dialogue)
    out = io.BytesIO()
    audio.export(out, format="mp3")
    return out.getvalue()
