# core/service/process/genai/voice_catalog.py
"""
音声合成の声(話者)の一覧(Audition・Castsタブの声の選択に使う。docs/architecture.md 9節)。

声の一覧はプロジェクトの音声合成の設定(project.yamlのgenai.tts)の提供元から取得する(core.genai.SpeechGenerator.list_voices)。
提供元は言語ごとの声を含めて数千件を返すことがあるので、取得した一覧を提供元・モデルごとに1時間だけ覚えておき、
言語(作品のoutput_language等。例: ja)は手元で絞り込む(ja→ja-JPのように、言語の部分が一致するもの)。
"""

import time
from typing import Optional

from core.genai import VoiceInfo
from core.project.project import Project
from core.service.process.genai.generator_builder import build_speech_generator

_CACHE_SECONDS = 60 * 60
_cache: dict[tuple[str, str], tuple[float, list[VoiceInfo]]] = {}


def matches_language(voice: VoiceInfo, language: Optional[str]) -> bool:
    """声が言語(ja・ja-JP等。Noneなら何でも)に合うか。言語の部分(ハイフンの前)が同じなら合う。"""
    if not language:
        return True
    code = (voice.language_code or "").lower()
    wanted = language.strip().lower()
    return code == wanted or code.split("-")[0] == wanted.split("-")[0]


def list_voices(project: Project, language: Optional[str] = None) -> list[VoiceInfo]:
    """プロジェクトの音声合成の提供元の声(languageに合うものだけ)。設定・APIキーが無ければValueError、
    提供元が一覧を返せなければNotImplementedError、取得の失敗はそのまま(requestsの例外等)。"""
    setting = project.tts
    if setting is None:
        raise ValueError("このプロジェクトには音声合成(TTS)の設定がありません。")
    key = (setting.client, setting.model)
    cached = _cache.get(key)
    if cached is None or time.monotonic() - cached[0] > _CACHE_SECONDS:
        cached = (time.monotonic(), build_speech_generator(project).list_voices())
        _cache[key] = cached
    return [voice for voice in cached[1] if matches_language(voice, language)]
