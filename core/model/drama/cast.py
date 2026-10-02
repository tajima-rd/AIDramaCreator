# core/model/drama/cast.py
"""
配役。人物(Character)と、その役の演じ方。台詞の話者になる。
どの声で演じるかは、演じるエージェント(core.model.agent.Actor)が持つ。
"""

from enum import StrEnum
from typing import Optional

from core.model.drama.character import Character
from core.model.identifier import new_id


class Performance:
    """役の演じ方。titleは短い見出し(例: Strict Guy)、descriptionはその説明、paceは話す速さ(例: 比較的ゆっくり)。"""

    def __init__(
        self,
        title: Optional[str] = None,
        description: Optional[str] = None,
        pace: Optional[str] = None,
    ):
        self.title: Optional[str] = title
        self.description: Optional[str] = description
        self.pace: Optional[str] = pace


class VoiceGender(StrEnum):
    """声を当てるときの性別。人物の性別(Character.gender。不明・両性もあり得る)とは別に、配役で決める。"""

    MALE = "male"
    FEMALE = "female"
    NEUTRAL = "neutral"  # 中性的


class CastBilling(StrEnum):
    """役の重さ(2026-10-02ユーザー決定)。台詞の無い人物には配役が無い。"""

    LEAD = "lead"  # 主役
    SUPPORTING = "supporting"  # 脇役
    MINOR = "minor"  # 端役(通行人A等)


class Cast:
    """characterは演じる人物、performanceは演じ方、voice_genderは声を当てるときの性別。languageは話す言語、
    accentは訛り・話しぶり、billingは役の重さ(主役・脇役・端役。未設定可)。演じ方・声の性別・言語・訛りが、
    声を選ぶ(Audition)ときの条件になる。"""

    def __init__(
        self,
        character: Character,
        performance: Optional[Performance] = None,
        voice_gender: Optional[VoiceGender] = None,
        language: Optional[str] = None,
        accent: Optional[str] = None,
        billing: Optional[CastBilling] = None,
    ):
        self.id: str = new_id()  # 識別子(不変)
        self.character: Character = character
        self.performance: Performance = performance if performance is not None else Performance()
        self.voice_gender: Optional[VoiceGender] = voice_gender
        self.language: Optional[str] = language
        self.accent: Optional[str] = accent
        self.billing: Optional[CastBilling] = billing
