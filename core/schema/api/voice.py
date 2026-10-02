# core/schema/api/voice.py
"""音声合成の声(話者)の一覧(core.service.api.voice)のDTO。"""

from typing import Optional

from pydantic import BaseModel


class VoiceSummary(BaseModel):
    voice_id: str  # 提供元の声の識別子(Actor.voice_nameに入れる値)
    display_name: Optional[str] = None
    language_code: Optional[str] = None
    gender: Optional[str] = None
    pitch: Optional[str] = None
    accent: Optional[str] = None
    persona: Optional[str] = None
    context: Optional[str] = None
    description: Optional[str] = None


class VoiceListResult(BaseModel):
    provider: str  # 音声合成の提供元(project.yamlのgenai.tts.client)
    model: str  # 音声合成のモデル
    voices: list[VoiceSummary]
