# core/model/drama/factory.py
"""
値から作品のエンティティを組み立てる関数(docs/model_design.md「モデルの組み立てと生成AIとの受け渡し」)。
DB・ファイルには触れず、組み立てたオブジェクトを返すだけ。モデル定義YAMLからの取り込み(core.infra.io.
model_definition_reader)と生成AIの提案の反映が、同じ組み立ての規則を共有するためにここへ置く。

識別子を持つエンティティのbuild_*は、キーワード引数idで既存の識別子を保てる(QIDMの_keeps_id)。
識別子を持たない値(Premise・Proposal・ProposalCharacter・Characteristic・AdditionalFeature・Performance・Situation・SpeechStyle・SentenceEnding・Script・History・Direction)は、クラスをそのまま使う。
"""

import functools
from typing import Optional

from core.model.agent.base_agent import BaseAgent
from core.model.drama.act import Act
from core.model.drama.cast import Cast, CastBilling, Performance, VoiceGender
from core.model.drama.character import Biography, Character
from core.model.drama.character_group import CharacterGroup
from core.model.drama.dramaturgy import Dramaturgy
from core.model.drama.feature import Characteristic
from core.model.drama.history import History
from core.model.drama.location import Location
from core.model.drama.premise import Premise
from core.model.drama.proposal import Proposal
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
    Translation,
)
from core.model.drama.site_flow import SiteFlow, SiteFlowDirection
from core.model.drama.situation import Situation
from core.model.drama.speech_style import SpeechStyle
from core.model.drama.temporal import (
    StringDateType,
    TemporalEdge,
    TemporalNode,
    TemporalRelationKind,
)


def _keeps_id(builder):
    """
    build_*に、キーワード引数id(既存のエンティティの識別子)を足す。指定すれば組み立てたエンティティの
    idをそれにし、省略すれば新しいidのまま(core.model.identifier)。
    """

    @functools.wraps(builder)
    def wrapper(*args, id: Optional[str] = None, **kwargs):
        entity = builder(*args, **kwargs)
        if id is not None:
            entity.id = id
        return entity

    return wrapper


@_keeps_id
def build_dramaturgy(
    title: str,
    synopsis: Optional[str] = None,
    input_language: Optional[str] = None,
    output_language: Optional[str] = None,
    premise: Optional[Premise] = None,
    characters: Optional[list[Character]] = None,
    relationships: Optional[list[Relationship]] = None,
    casts: Optional[list[Cast]] = None,
    acts: Optional[list[Act]] = None,
    history: Optional[History] = None,
    proposal: Optional[Proposal] = None,
    agents: Optional[list[BaseAgent]] = None,
    locations: Optional[list[Location]] = None,
    site_flows: Optional[list[SiteFlow]] = None,
) -> Dramaturgy:
    return Dramaturgy(
        title,
        synopsis,
        input_language,
        output_language,
        premise,
        characters,
        relationships,
        casts,
        acts,
        history,
        proposal,
        agents,
        locations,
        site_flows,
    )


@_keeps_id
def build_temporal_node(
    label: Optional[str] = None,
    date_type: Optional[str] = None,
    string_date: Optional[str] = None,
) -> TemporalNode:
    return TemporalNode(
        label,
        StringDateType(date_type) if date_type is not None else None,
        string_date,
    )


@_keeps_id
def build_temporal_edge(
    source: TemporalNode,
    target: TemporalNode,
    kind: str,
    label: Optional[str] = None,
) -> TemporalEdge:
    return TemporalEdge(source, target, TemporalRelationKind(kind), label)


@_keeps_id
def build_location(
    name: str,
    geometry: Optional[str] = None,
    address: Optional[str] = None,
    instruction: Optional[str] = None,
    description: Optional[str] = None,
) -> Location:
    return Location(name, geometry, address, instruction, description)


@_keeps_id
def build_site_flow(
    origin: Location,
    destination: Location,
    direction: Optional[str] = None,
    geometry: Optional[str] = None,
    name: Optional[str] = None,
) -> SiteFlow:
    return SiteFlow(
        origin,
        destination,
        SiteFlowDirection(direction) if direction is not None else None,
        geometry,
        name,
    )


@_keeps_id
def build_character(
    name: str,
    reading: Optional[str] = None,
    gender: Optional[str] = None,
    age: Optional[str] = None,
    speech_style: Optional[SpeechStyle] = None,
    characteristics: Optional[list[Characteristic]] = None,
    biographies: Optional[list[Biography]] = None,
) -> Character:
    return Character(name, reading, gender, age, speech_style, characteristics, biographies)


@_keeps_id
def build_character_group(
    name: str,
    kind: Optional[str] = None,
    members: Optional[list[Character]] = None,
    description: Optional[str] = None,
) -> CharacterGroup:
    return CharacterGroup(name, kind, members, description)


@_keeps_id
def build_biography(
    period: TemporalNode,
    episode: str,
    involved_relationships: Optional[list[Relationship]] = None,
) -> Biography:
    return Biography(period, episode, involved_relationships)


@_keeps_id
def build_relationship(
    source: Character,
    target: Character,
    label: str,
    period: Optional[TemporalNode] = None,
    description: Optional[str] = None,
    form_of_address: Optional[str] = None,
    tone: Optional[str] = None,
) -> Relationship:
    return Relationship(source, target, label, period, description, form_of_address, tone)


@_keeps_id
def build_cast(
    character: Character,
    performance: Optional[Performance] = None,
    voice_gender: Optional[str] = None,
    language: Optional[str] = None,
    accent: Optional[str] = None,
    billing: Optional[str] = None,
) -> Cast:
    return Cast(
        character,
        performance,
        VoiceGender(voice_gender) if voice_gender is not None else None,
        language,
        accent,
        CastBilling(billing) if billing is not None else None,
    )


@_keeps_id
def build_act(
    order: int,
    title: Optional[str] = None,
    synopsis: Optional[str] = None,
    scenes: Optional[list[Scene]] = None,
) -> Act:
    return Act(order, title, synopsis, scenes)


@_keeps_id
def build_scene(
    order: int,
    title: Optional[str] = None,
    synopsis: Optional[str] = None,
    period: Optional[TemporalNode] = None,
    location: Optional[Location] = None,
    situation: Optional[Situation] = None,
    script: Optional[Script] = None,
    elements: Optional[list[ScriptElement]] = None,
) -> Scene:
    return Scene(order, title, synopsis, period, location, situation, script, elements)


@_keeps_id
def build_line(order: int, cast: Cast, text: str) -> Line:
    return Line(order, cast, text)


@_keeps_id
def build_dialogue(
    order: int,
    line_id: str,
    cast_id: str,
    text: str,
    action: Optional[str] = None,
    direction: Optional[Direction] = None,
    translations: Optional[list[Translation]] = None,
    situation: Optional[Situation] = None,
) -> Dialogue:
    return Dialogue(order, line_id, cast_id, text, action, direction, translations, situation)


# 固有の属性を持たない原稿の要素。種類の名前(モデル定義YAMLのtype)→クラス
_PLAIN_ELEMENT_TYPES: dict[str, type[ScriptElement]] = {
    "sound_effect": SoundEffect,
    "atmosphere": Atmosphere,
    "music": Music,
}


@_keeps_id
def build_plain_element(element_type: str, order: int) -> ScriptElement:
    """固有の属性を持たない原稿の要素(効果音・環境音・BGM)。element_typeはsound_effect・atmosphere・music。"""
    if element_type not in _PLAIN_ELEMENT_TYPES:
        raise ValueError(f"原稿の要素の種類 '{element_type}' はありません")
    return _PLAIN_ELEMENT_TYPES[element_type](order)
