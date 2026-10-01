# core/model/drama/character.py
"""
人物と経歴。物語に直接出てこない人物もCharacterとして設定する(声の割り当てが無い人物になる)。
経歴はハルシネーション対策として重要なので、人物像とは別に、時期ごとのBiographyとして持つ。
"""

from typing import Optional

from core.model.drama.feature import Characteristic
from core.model.drama.relationship import Relationship
from core.model.drama.speech_style import SpeechStyle
from core.model.drama.temporal import TemporalNode
from core.model.identifier import new_id


class Biography:
    """経歴の1項目。ある時期(TemporalNode)の出来事と、それに関わる人物関係(Relationship。複数でもよい)。"""

    def __init__(
        self,
        period: TemporalNode,
        episode: str,
        involved_relationships: Optional[list[Relationship]] = None,
    ):
        self.id: str = new_id()  # 識別子(不変)
        self.period: TemporalNode = period
        self.episode: str = episode
        self.involved_relationships: list[Relationship] = list(involved_relationships or [])


class Character:
    """人物。speech_styleは話し方(一人称・口調・語尾。core.model.drama.speech_style)。相手によって変わる呼び方・口調は
    人物関係(Relationship.form_of_address・tone)が持つ。characteristicsは人物像の特徴(項目は作品によって変わるので決め打ちにしない。
    core.model.drama.feature)。"""

    def __init__(
        self,
        name: str,
        reading: Optional[str] = None,
        gender: Optional[str] = None,
        age: Optional[str] = None,
        speech_style: Optional[SpeechStyle] = None,
        characteristics: Optional[list[Characteristic]] = None,
        biographies: Optional[list[Biography]] = None,
    ):
        self.id: str = new_id()  # 識別子(不変)。nameは変更できる名前
        self.name: str = name
        self.reading: Optional[str] = reading
        self.gender: Optional[str] = gender
        self.age: Optional[str] = age
        self.speech_style: SpeechStyle = speech_style if speech_style is not None else SpeechStyle()
        self.characteristics: list[Characteristic] = list(characteristics or [])
        self.biographies: list[Biography] = list(biographies or [])
        # この人物が関わる人物関係(sourceでもtargetでも)。Relationshipを作ると、両端の人物に加わる(所有はしない)
        self.relationships: list[Relationship] = []
