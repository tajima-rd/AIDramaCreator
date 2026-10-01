# core/model/drama/__init__.py
"""
作られる作品のモデル(docs/model_design.md)。クラスと属性だけを定義している(機能は合意してから加える)。
"""

from core.model.drama.act import Act
from core.model.drama.cast import Cast
from core.model.drama.character import Biography, Character
from core.model.drama.dramaturgy import Dramaturgy
from core.model.drama.feature import AdditionalFeature, Characteristic
from core.model.drama.history import History
from core.model.drama.location import Location
from core.model.drama.premise import Premise
from core.model.drama.relationship import Relationship
from core.model.drama.scene import Scene
from core.model.drama.script import Line, Script
from core.model.drama.script_element import (
    Atmosphere,
    Dialogue,
    Direction,
    Music,
    ScriptElement,
    SoundEffect,
)
from core.model.drama.temporal import (
    StringDateType,
    TemporalEdge,
    TemporalNode,
    TemporalRelationKind,
)

__all__ = [
    "Act",
    "AdditionalFeature",
    "Atmosphere",
    "Biography",
    "Cast",
    "Character",
    "Characteristic",
    "Dialogue",
    "Direction",
    "Dramaturgy",
    "History",
    "Line",
    "Location",
    "Music",
    "Premise",
    "Relationship",
    "Scene",
    "Script",
    "ScriptElement",
    "SoundEffect",
    "StringDateType",
    "TemporalEdge",
    "TemporalNode",
    "TemporalRelationKind",
]
