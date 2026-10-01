# core/model/drama/scene.py
"""
シーン。あらすじ・台詞(Script)・演出付きの原稿(elements)を持つ。periodは描く時期で、
語りの順(order)とは別(回想等。暫定)。locationは場所、situationは場面の状況(状況・時間帯・天候等。台詞で上書きできる)。
"""

from typing import Optional

from core.model.drama.location import Location
from core.model.drama.script import Script
from core.model.drama.script_element import ScriptElement
from core.model.drama.situation import Situation
from core.model.drama.temporal import TemporalNode
from core.model.identifier import new_id


class Scene:
    """幕の中のシーン。synopsisはシーンのあらすじ。"""

    def __init__(
        self,
        order: int,
        title: Optional[str] = None,
        synopsis: Optional[str] = None,
        period: Optional[TemporalNode] = None,
        location: Optional[Location] = None,
        situation: Optional[Situation] = None,
        script: Optional[Script] = None,
        elements: Optional[list[ScriptElement]] = None,
    ):
        self.id: str = new_id()  # 識別子(不変)
        self.order: int = order
        self.title: Optional[str] = title
        self.synopsis: Optional[str] = synopsis
        self.period: Optional[TemporalNode] = period
        self.location: Optional[Location] = location
        self.situation: Situation = situation if situation is not None else Situation()
        self.script: Script = script if script is not None else Script()
        self.elements: list[ScriptElement] = list(elements or [])
