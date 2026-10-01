# core/model/drama/temporal.py
"""
時間の位相(Temporal Topology)。時間の順序は1次元ではなく、時点(TemporalNode)と、時点どうしの関係
(TemporalEdge)で表す。どのTemporalNodeも、ほかのTemporalNodeとの関係を少なくとも1つ持つ(docs/model_design.md)。
"""

from enum import StrEnum
from typing import Optional

from core.model.identifier import new_id


class TemporalRelationKind(StrEnum):
    """2つのTemporalNodeの関係(Allenの区間代数)。sourceから見たtargetとの関係。"""

    BEFORE = "before"
    MEETS = "meets"
    OVERLAPS = "overlaps"
    DURING = "during"
    STARTS = "starts"
    FINISHES = "finishes"
    EQUALS = "equals"


class StringDateType(StrEnum):
    """string_dateの書き方の種類。STRING_EXPRESSIONは日付にならない言葉(例: 明治の末ごろ)。"""

    DATETIME = "datetime"
    DATE = "date"
    YEAR = "year"
    MONTH = "month"
    DAY = "day"
    TIME = "time"
    HOUR = "hour"
    MINUTES = "minutes"
    SECONDS = "seconds"
    STRING_EXPRESSION = "string_expression"


class TemporalNode:
    """時点(時期)。labelは言葉としての時期(例: 中学校時代)、string_dateは日付・年代で、date_typeがその書き方。
    どれも任意。"""

    def __init__(
        self,
        label: Optional[str] = None,
        date_type: Optional[StringDateType] = None,
        string_date: Optional[str] = None,
    ):
        self.id: str = new_id()  # 識別子(不変)
        self.label: Optional[str] = label
        self.date_type: Optional[StringDateType] = date_type
        self.string_date: Optional[str] = string_date


class TemporalEdge:
    """sourceから見たtargetとの関係。"""

    def __init__(
        self,
        source: TemporalNode,
        target: TemporalNode,
        kind: TemporalRelationKind,
        label: Optional[str] = None,
    ):
        self.id: str = new_id()  # 識別子(不変)
        self.label: Optional[str] = label
        self.kind: TemporalRelationKind = kind
        self.source: TemporalNode = source
        self.target: TemporalNode = target
