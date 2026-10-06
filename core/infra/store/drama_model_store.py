# core/infra/store/drama_model_store.py
"""
プロジェクトのDB(project.db)にある、作品モデル(core.model.drama)の正本のテーブルの読み書き
(docs/database_design.md「B. ① 正本」)。プロジェクトの作品モデル全体をModelDefinitionとして扱う。

正本を変える経路は下書きの確定だけ(docs/architecture.md 7節)。そのため、書き込み(write_model)は接続を受け取り、
確定の手順(core.service.process.edit.drama_draft_editor)が版の記録と同じトランザクションの中で呼ぶ。
write_modelは、すべての行を消してから書き直す(コミットしない)。

- 識別子を持つものは1クラス=1テーブル。1つだけ持つ値(Premise・Situation・Direction・Performance・SpeechStyle)は
  持ち主の列、一覧で持つ値(Characteristic→AdditionalFeature・SentenceEnding・ProposalCharacter)は持ち主のidと並び順で
  特定する子テーブル。企画書(Proposal)は登場人物の一覧を持つため、作品ごとに1行のproposalテーブルにする。
- ScriptElementは1テーブル+種別の列(kind)。Dialogue.line_id・cast_idはID参照なので外部キーの制約を付けない。
- sort_orderは、Act・Scene・Line・ScriptElementではモデルのorder、それ以外は一覧の中の位置。並びの無い一覧(人物・場所等)は
  書いた順(rowid)に読む。
- Character.relationshipsは保存しない(人物関係を組み立てるとそろう)。
- 場所(location)・移動(site_flow)は形の列(geom)を持つGeoPackageの地物の表(core.gis.io.geopackage。2026-10-02)。
  GeoPackageは地物の表に整数の主キーを求めるので、この2つはfid(整数)を主キーにし、識別子(id)は一意の列にする。
- エージェント(core.model.agent。作品が所有する)は1テーブル+職能の列(kind)。rules・prohibitions(文字列の一覧)はJSONの列、
  タスクはagent_task(並び順はタスクの並び。codeで特定)。Actor.casting_idはID参照なので外部キーの制約を付けない。
"""

import json
import sqlite3
from typing import Any, Optional

from core.gis.io.geopackage import decode_geometry, encode_geometry, ensure_geopackage
from core.infra.io.model_definition_reader import ModelDefinition
from core.model.agent import Actor, AgentTask, BaseAgent, LanguageVoice
from core.model.agent.factory import AGENT_ROLES, build_actor, build_agent
from core.model.drama import (
    AdditionalFeature,
    Atmosphere,
    Character,
    Characteristic,
    Dialogue,
    Direction,
    Dramaturgy,
    History,
    Music,
    Performance,
    Premise,
    Proposal,
    ProposalCharacter,
    Relationship,
    Script,
    ScriptElement,
    SentenceEnding,
    SentenceEndingKind,
    Situation,
    SoundEffect,
    SpeechStyle,
    TemporalNode,
    Translation,
)
from core.model.drama.factory import (
    build_act,
    build_biography,
    build_cast,
    build_character,
    build_character_group,
    build_dialogue,
    build_dramaturgy,
    build_line,
    build_location,
    build_plain_element,
    build_relationship,
    build_scene,
    build_site_flow,
    build_temporal_edge,
    build_temporal_node,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS temporal_node (
    id TEXT PRIMARY KEY,
    label TEXT,
    date_type TEXT,
    string_date TEXT
);
CREATE TABLE IF NOT EXISTS location (
    fid INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    geom BLOB,
    address TEXT,
    instruction TEXT,
    description TEXT
);
CREATE TABLE IF NOT EXISTS site_flow (
    fid INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    name TEXT,
    geom BLOB,
    direction TEXT,
    origin_id TEXT NOT NULL REFERENCES location(id),
    destination_id TEXT NOT NULL REFERENCES location(id)
);
CREATE TABLE IF NOT EXISTS character (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    reading TEXT,
    gender TEXT,
    age TEXT,
    speech_first_person TEXT,
    speech_tone TEXT,
    speech_description TEXT
);
CREATE TABLE IF NOT EXISTS sentence_ending (
    character_id TEXT NOT NULL REFERENCES character(id) ON DELETE CASCADE,
    sort_order INTEGER NOT NULL,
    kind TEXT NOT NULL,
    examples TEXT NOT NULL,
    description TEXT,
    PRIMARY KEY (character_id, sort_order)
);
CREATE TABLE IF NOT EXISTS characteristic (
    character_id TEXT NOT NULL REFERENCES character(id) ON DELETE CASCADE,
    sort_order INTEGER NOT NULL,
    item TEXT NOT NULL,
    definition TEXT,
    description TEXT,
    PRIMARY KEY (character_id, sort_order)
);
CREATE TABLE IF NOT EXISTS additional_feature (
    character_id TEXT NOT NULL,
    characteristic_order INTEGER NOT NULL,
    sort_order INTEGER NOT NULL,
    item TEXT NOT NULL,
    value TEXT,
    definition TEXT,
    description TEXT,
    PRIMARY KEY (character_id, characteristic_order, sort_order),
    FOREIGN KEY (character_id, characteristic_order)
        REFERENCES characteristic(character_id, sort_order) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS biography (
    id TEXT PRIMARY KEY,
    character_id TEXT NOT NULL REFERENCES character(id) ON DELETE CASCADE,
    sort_order INTEGER NOT NULL,
    period_id TEXT NOT NULL REFERENCES temporal_node(id),
    episode TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS character_group (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT,
    description TEXT
);
CREATE TABLE IF NOT EXISTS relationship (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES character(id),
    target_id TEXT NOT NULL REFERENCES character(id),
    label TEXT NOT NULL,
    period_id TEXT REFERENCES temporal_node(id),
    description TEXT,
    form_of_address TEXT,
    tone TEXT
);
CREATE TABLE IF NOT EXISTS dramaturgy (
    id TEXT PRIMARY KEY,
    sort_order INTEGER NOT NULL,
    title TEXT NOT NULL,
    synopsis TEXT,
    input_language TEXT,
    output_language TEXT,
    premise_text TEXT
);
CREATE TABLE IF NOT EXISTS proposal (
    dramaturgy_id TEXT PRIMARY KEY REFERENCES dramaturgy(id) ON DELETE CASCADE,
    title TEXT,
    catchphrase TEXT,
    logline TEXT,
    intent TEXT,
    target_area TEXT,
    synopsis TEXT
);
CREATE TABLE IF NOT EXISTS agent (
    id TEXT PRIMARY KEY,
    dramaturgy_id TEXT NOT NULL REFERENCES dramaturgy(id) ON DELETE CASCADE,
    sort_order INTEGER NOT NULL,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    persona TEXT,
    rules TEXT NOT NULL,
    prohibitions TEXT NOT NULL,
    casting_id TEXT,
    voice_name TEXT,
    tts_provider TEXT,
    tts_model TEXT
);
CREATE TABLE IF NOT EXISTS agent_voice (
    agent_id TEXT NOT NULL REFERENCES agent(id) ON DELETE CASCADE,
    sort_order INTEGER NOT NULL,
    language TEXT NOT NULL,
    voice_name TEXT NOT NULL,
    tts_provider TEXT,
    tts_model TEXT,
    PRIMARY KEY (agent_id, language)
);
CREATE TABLE IF NOT EXISTS agent_task (
    agent_id TEXT NOT NULL REFERENCES agent(id) ON DELETE CASCADE,
    sort_order INTEGER NOT NULL,
    code TEXT NOT NULL,
    title TEXT,
    description TEXT,
    rules TEXT NOT NULL,
    prohibitions TEXT NOT NULL,
    PRIMARY KEY (agent_id, code)
);
CREATE TABLE IF NOT EXISTS proposal_character (
    dramaturgy_id TEXT NOT NULL REFERENCES proposal(dramaturgy_id) ON DELETE CASCADE,
    sort_order INTEGER NOT NULL,
    name TEXT,
    description TEXT,
    PRIMARY KEY (dramaturgy_id, sort_order)
);
CREATE TABLE IF NOT EXISTS temporal_edge (
    id TEXT PRIMARY KEY,
    dramaturgy_id TEXT NOT NULL REFERENCES dramaturgy(id) ON DELETE CASCADE,
    sort_order INTEGER NOT NULL,
    label TEXT,
    kind TEXT NOT NULL,
    source_id TEXT NOT NULL REFERENCES temporal_node(id),
    target_id TEXT NOT NULL REFERENCES temporal_node(id)
);
CREATE TABLE IF NOT EXISTS "cast" (
    id TEXT PRIMARY KEY,
    dramaturgy_id TEXT NOT NULL REFERENCES dramaturgy(id) ON DELETE CASCADE,
    sort_order INTEGER NOT NULL,
    character_id TEXT NOT NULL REFERENCES character(id),
    performance_title TEXT,
    performance_description TEXT,
    performance_pace TEXT,
    voice_gender TEXT,
    language TEXT,
    accent TEXT,
    billing TEXT
);
CREATE TABLE IF NOT EXISTS act (
    id TEXT PRIMARY KEY,
    dramaturgy_id TEXT NOT NULL REFERENCES dramaturgy(id) ON DELETE CASCADE,
    sort_order INTEGER NOT NULL,
    title TEXT,
    synopsis TEXT
);
CREATE TABLE IF NOT EXISTS scene (
    id TEXT PRIMARY KEY,
    act_id TEXT NOT NULL REFERENCES act(id) ON DELETE CASCADE,
    sort_order INTEGER NOT NULL,
    title TEXT,
    synopsis TEXT,
    period_id TEXT REFERENCES temporal_node(id),
    location_id TEXT REFERENCES location(id),
    situation_location_id TEXT REFERENCES location(id),
    situation_description TEXT,
    situation_time_of_day TEXT,
    situation_environment TEXT
);
CREATE TABLE IF NOT EXISTS line (
    id TEXT PRIMARY KEY,
    scene_id TEXT NOT NULL REFERENCES scene(id) ON DELETE CASCADE,
    sort_order INTEGER NOT NULL,
    cast_id TEXT NOT NULL REFERENCES "cast"(id),
    text TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS script_element (
    id TEXT PRIMARY KEY,
    scene_id TEXT NOT NULL REFERENCES scene(id) ON DELETE CASCADE,
    sort_order INTEGER NOT NULL,
    kind TEXT NOT NULL,
    line_id TEXT,
    cast_id TEXT,
    text TEXT,
    action TEXT,
    direction_style TEXT,
    direction_pace TEXT,
    direction_dynamics TEXT,
    direction_emotion TEXT,
    direction_pause_after TEXT,
    has_situation INTEGER NOT NULL DEFAULT 0,
    situation_location_id TEXT REFERENCES location(id),
    situation_description TEXT,
    situation_time_of_day TEXT,
    situation_environment TEXT
);
CREATE TABLE IF NOT EXISTS script_element_translation (
    element_id TEXT NOT NULL REFERENCES script_element(id) ON DELETE CASCADE,
    sort_order INTEGER NOT NULL,
    language TEXT NOT NULL,
    text TEXT NOT NULL,
    PRIMARY KEY (element_id, language)
);
CREATE TABLE IF NOT EXISTS dramaturgy_character (
    dramaturgy_id TEXT NOT NULL REFERENCES dramaturgy(id) ON DELETE CASCADE,
    character_id TEXT NOT NULL REFERENCES character(id) ON DELETE CASCADE,
    sort_order INTEGER NOT NULL,
    PRIMARY KEY (dramaturgy_id, character_id)
);
CREATE TABLE IF NOT EXISTS dramaturgy_relationship (
    dramaturgy_id TEXT NOT NULL REFERENCES dramaturgy(id) ON DELETE CASCADE,
    relationship_id TEXT NOT NULL REFERENCES relationship(id) ON DELETE CASCADE,
    sort_order INTEGER NOT NULL,
    PRIMARY KEY (dramaturgy_id, relationship_id)
);
CREATE TABLE IF NOT EXISTS dramaturgy_location (
    dramaturgy_id TEXT NOT NULL REFERENCES dramaturgy(id) ON DELETE CASCADE,
    location_id TEXT NOT NULL REFERENCES location(id) ON DELETE CASCADE,
    sort_order INTEGER NOT NULL,
    PRIMARY KEY (dramaturgy_id, location_id)
);
CREATE TABLE IF NOT EXISTS dramaturgy_site_flow (
    dramaturgy_id TEXT NOT NULL REFERENCES dramaturgy(id) ON DELETE CASCADE,
    site_flow_id TEXT NOT NULL REFERENCES site_flow(id) ON DELETE CASCADE,
    sort_order INTEGER NOT NULL,
    PRIMARY KEY (dramaturgy_id, site_flow_id)
);
CREATE TABLE IF NOT EXISTS character_group_member (
    character_group_id TEXT NOT NULL REFERENCES character_group(id) ON DELETE CASCADE,
    character_id TEXT NOT NULL REFERENCES character(id) ON DELETE CASCADE,
    sort_order INTEGER NOT NULL,
    PRIMARY KEY (character_group_id, character_id)
);
CREATE TABLE IF NOT EXISTS biography_relationship (
    biography_id TEXT NOT NULL REFERENCES biography(id) ON DELETE CASCADE,
    relationship_id TEXT NOT NULL REFERENCES relationship(id) ON DELETE CASCADE,
    sort_order INTEGER NOT NULL,
    PRIMARY KEY (biography_id, relationship_id)
);
"""

# すべての行を消すときの順(参照する側から)
_TABLES = (
    "biography_relationship",
    "character_group_member",
    "dramaturgy_site_flow",
    "dramaturgy_location",
    "dramaturgy_relationship",
    "dramaturgy_character",
    "script_element_translation",
    "script_element",
    "line",
    "scene",
    "act",
    '"cast"',
    "temporal_edge",
    "agent_task",
    "agent_voice",
    "agent",
    "proposal_character",
    "proposal",
    "dramaturgy",
    "relationship",
    "character_group",
    "biography",
    "additional_feature",
    "characteristic",
    "sentence_ending",
    "character",
    "site_flow",
    "location",
    "temporal_node",
)

# エージェントのクラス→職能の列(kind)の値。値はモデル定義YAMLの区画名の単数形
_AGENT_KINDS: dict[type[BaseAgent], str] = {
    **{cls: name for name, cls in AGENT_ROLES.items()},
    Actor: "actor",
}

# 原稿の要素のクラス→種別の列(kind)の値。値はモデル定義YAMLのtypeと同じ
_ELEMENT_KINDS: dict[type[ScriptElement], str] = {
    Dialogue: "dialogue",
    SoundEffect: "sound_effect",
    Atmosphere: "atmosphere",
    Music: "music",
}


def ensure_schema(conn: sqlite3.Connection) -> None:
    """作品のテーブルが無ければ作る。場所・移動の表はGeoPackageの地物の表として登録する。"""
    conn.executescript(_SCHEMA)
    ensure_geopackage(conn, {"location": ("geom", "GEOMETRY"), "site_flow": ("geom", "LINESTRING")})


def _insert(conn: sqlite3.Connection, table: str, values: dict[str, Any]) -> None:
    columns = ", ".join(values)
    marks = ", ".join("?" for _ in values)
    conn.execute(f"INSERT INTO {table} ({columns}) VALUES ({marks})", tuple(values.values()))


def _id(entity: Any) -> Optional[str]:
    return entity.id if entity is not None else None


def _enum(value: Any) -> Optional[str]:
    return value.value if value is not None else None


def _situation_columns(situation: Optional[Situation]) -> dict[str, Any]:
    situation = situation or Situation()
    return {
        "situation_location_id": _id(situation.location),
        "situation_description": situation.description,
        "situation_time_of_day": situation.time_of_day,
        "situation_environment": situation.environment,
    }


def write_model(conn: sqlite3.Connection, definition: ModelDefinition) -> None:
    """
    正本のすべての行を消し、definition(プロジェクトの作品モデル全体)を書く。コミットしない(呼ぶ側のトランザクション)。
    外部キーの検査はコミットの時まで遅らせる(書く順に左右されないため)。
    """
    conn.execute("PRAGMA defer_foreign_keys = ON")
    for table in _TABLES:
        conn.execute(f"DELETE FROM {table}")

    for node in definition.temporal_nodes:
        _insert(
            conn,
            "temporal_node",
            {
                "id": node.id,
                "label": node.label,
                "date_type": _enum(node.date_type),
                "string_date": node.string_date,
            },
        )
    for location in definition.locations:
        _insert(
            conn,
            "location",
            {
                "id": location.id,
                "name": location.name,
                "geom": encode_geometry(location.geometry),
                "address": location.address,
                "instruction": location.instruction,
                "description": location.description,
            },
        )
    for flow in definition.site_flows:
        _insert(
            conn,
            "site_flow",
            {
                "id": flow.id,
                "name": flow.name,
                "geom": encode_geometry(flow.geometry),
                "direction": _enum(flow.direction),
                "origin_id": flow.origin.id,
                "destination_id": flow.destination.id,
            },
        )
    for character in definition.characters:
        _write_character(conn, character)
    for group in definition.character_groups:
        _insert(
            conn,
            "character_group",
            {
                "id": group.id,
                "name": group.name,
                "kind": group.kind,
                "description": group.description,
            },
        )
        for index, member in enumerate(group.members):
            _insert(
                conn,
                "character_group_member",
                {"character_group_id": group.id, "character_id": member.id, "sort_order": index},
            )
    for relationship in definition.relationships:
        _insert(
            conn,
            "relationship",
            {
                "id": relationship.id,
                "source_id": relationship.source.id,
                "target_id": relationship.target.id,
                "label": relationship.label,
                "period_id": _id(relationship.period),
                "description": relationship.description,
                "form_of_address": relationship.form_of_address,
                "tone": relationship.tone,
            },
        )
    for character in definition.characters:
        for index, biography in enumerate(character.biographies):
            _insert(
                conn,
                "biography",
                {
                    "id": biography.id,
                    "character_id": character.id,
                    "sort_order": index,
                    "period_id": biography.period.id,
                    "episode": biography.episode,
                },
            )
            for position, relationship in enumerate(biography.involved_relationships):
                _insert(
                    conn,
                    "biography_relationship",
                    {
                        "biography_id": biography.id,
                        "relationship_id": relationship.id,
                        "sort_order": position,
                    },
                )
    for index, dramaturgy in enumerate(definition.dramaturgies):
        _write_dramaturgy(conn, dramaturgy, index)


def _write_character(conn: sqlite3.Connection, character: Character) -> None:
    style = character.speech_style
    _insert(
        conn,
        "character",
        {
            "id": character.id,
            "name": character.name,
            "reading": character.reading,
            "gender": character.gender,
            "age": character.age,
            "speech_first_person": style.first_person,
            "speech_tone": style.tone,
            "speech_description": style.description,
        },
    )
    for index, ending in enumerate(style.endings):
        _insert(
            conn,
            "sentence_ending",
            {
                "character_id": character.id,
                "sort_order": index,
                "kind": ending.kind.value,
                "examples": json.dumps(ending.examples, ensure_ascii=False),
                "description": ending.description,
            },
        )
    for index, characteristic in enumerate(character.characteristics):
        _insert(
            conn,
            "characteristic",
            {
                "character_id": character.id,
                "sort_order": index,
                "item": characteristic.item,
                "definition": characteristic.definition,
                "description": characteristic.description,
            },
        )
        for position, feature in enumerate(characteristic.features):
            _insert(
                conn,
                "additional_feature",
                {
                    "character_id": character.id,
                    "characteristic_order": index,
                    "sort_order": position,
                    "item": feature.item,
                    "value": feature.value,
                    "definition": feature.definition,
                    "description": feature.description,
                },
            )


def _write_dramaturgy(conn: sqlite3.Connection, dramaturgy: Dramaturgy, index: int) -> None:
    _insert(
        conn,
        "dramaturgy",
        {
            "id": dramaturgy.id,
            "sort_order": index,
            "title": dramaturgy.title,
            "synopsis": dramaturgy.synopsis,
            "input_language": dramaturgy.input_language,
            "output_language": dramaturgy.output_language,
            "premise_text": dramaturgy.premise.text,
        },
    )
    proposal = dramaturgy.proposal
    _insert(
        conn,
        "proposal",
        {
            "dramaturgy_id": dramaturgy.id,
            "title": proposal.title,
            "catchphrase": proposal.catchphrase,
            "logline": proposal.logline,
            "intent": proposal.intent,
            "target_area": proposal.target_area,
            "synopsis": proposal.synopsis,
        },
    )
    for position, agent in enumerate(dramaturgy.agents):
        _write_agent(conn, dramaturgy.id, agent, position)
    for position, character in enumerate(proposal.characters):
        _insert(
            conn,
            "proposal_character",
            {
                "dramaturgy_id": dramaturgy.id,
                "sort_order": position,
                "name": character.name,
                "description": character.description,
            },
        )
    for position, character in enumerate(dramaturgy.characters):
        _insert(
            conn,
            "dramaturgy_character",
            {"dramaturgy_id": dramaturgy.id, "character_id": character.id, "sort_order": position},
        )
    for position, relationship in enumerate(dramaturgy.relationships):
        _insert(
            conn,
            "dramaturgy_relationship",
            {
                "dramaturgy_id": dramaturgy.id,
                "relationship_id": relationship.id,
                "sort_order": position,
            },
        )
    for position, location in enumerate(dramaturgy.locations):
        _insert(
            conn,
            "dramaturgy_location",
            {"dramaturgy_id": dramaturgy.id, "location_id": location.id, "sort_order": position},
        )
    for position, flow in enumerate(dramaturgy.site_flows):
        _insert(
            conn,
            "dramaturgy_site_flow",
            {"dramaturgy_id": dramaturgy.id, "site_flow_id": flow.id, "sort_order": position},
        )
    for position, edge in enumerate(dramaturgy.history.edges):
        _insert(
            conn,
            "temporal_edge",
            {
                "id": edge.id,
                "dramaturgy_id": dramaturgy.id,
                "sort_order": position,
                "label": edge.label,
                "kind": edge.kind.value,
                "source_id": edge.source.id,
                "target_id": edge.target.id,
            },
        )
    for position, cast in enumerate(dramaturgy.casts):
        _insert(
            conn,
            '"cast"',
            {
                "id": cast.id,
                "dramaturgy_id": dramaturgy.id,
                "sort_order": position,
                "character_id": cast.character.id,
                "performance_title": cast.performance.title,
                "performance_description": cast.performance.description,
                "performance_pace": cast.performance.pace,
                "voice_gender": _enum(cast.voice_gender),
                "language": cast.language,
                "accent": cast.accent,
                "billing": _enum(cast.billing),
            },
        )
    for act in dramaturgy.acts:
        _insert(
            conn,
            "act",
            {
                "id": act.id,
                "dramaturgy_id": dramaturgy.id,
                "sort_order": act.order,
                "title": act.title,
                "synopsis": act.synopsis,
            },
        )
        for scene in act.scenes:
            _insert(
                conn,
                "scene",
                {
                    "id": scene.id,
                    "act_id": act.id,
                    "sort_order": scene.order,
                    "title": scene.title,
                    "synopsis": scene.synopsis,
                    "period_id": _id(scene.period),
                    "location_id": _id(scene.location),
                    **_situation_columns(scene.situation),
                },
            )
            for line in scene.script.lines:
                _insert(
                    conn,
                    "line",
                    {
                        "id": line.id,
                        "scene_id": scene.id,
                        "sort_order": line.order,
                        "cast_id": line.cast.id,
                        "text": line.text,
                    },
                )
            for element in scene.elements:
                _write_element(conn, scene.id, element)


def _write_element(conn: sqlite3.Connection, scene_id: str, element: ScriptElement) -> None:
    if type(element) not in _ELEMENT_KINDS:
        raise ValueError(f"DBに書けない原稿の要素です: {type(element).__name__}")
    values: dict[str, Any] = {
        "id": element.id,
        "scene_id": scene_id,
        "sort_order": element.order,
        "kind": _ELEMENT_KINDS[type(element)],
    }
    if isinstance(element, Dialogue):
        direction = element.direction
        values.update(
            {
                "line_id": element.line_id,
                "cast_id": element.cast_id,
                "text": element.text,
                "action": element.action,
                "direction_style": direction.style,
                "direction_pace": direction.pace,
                "direction_dynamics": direction.dynamics,
                "direction_emotion": direction.emotion,
                "direction_pause_after": direction.pause_after,
                "has_situation": 1 if element.situation is not None else 0,
                **_situation_columns(element.situation),
            }
        )
    _insert(conn, "script_element", values)
    if isinstance(element, Dialogue):
        for order, translation in enumerate(element.translations):
            _insert(
                conn,
                "script_element_translation",
                {"element_id": element.id, "sort_order": order, "language": translation.language, "text": translation.text},
            )


def _rows(conn: sqlite3.Connection, sql: str, *params: Any) -> list[sqlite3.Row]:
    cursor = conn.execute(sql, params)
    cursor.row_factory = sqlite3.Row
    return cursor.fetchall()


def _grouped(rows: list[sqlite3.Row], key: str) -> dict[str, list[sqlite3.Row]]:
    groups: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        groups.setdefault(row[key], []).append(row)
    return groups


def _situation(row: sqlite3.Row, locations: dict[str, Any]) -> Situation:
    return Situation(
        locations[row["situation_location_id"]] if row["situation_location_id"] else None,
        row["situation_description"],
        row["situation_time_of_day"],
        row["situation_environment"],
    )


def _write_agent(
    conn: sqlite3.Connection, dramaturgy_id: str, agent: BaseAgent, position: int
) -> None:
    kind = _AGENT_KINDS.get(type(agent))
    if kind is None:
        raise ValueError(f"保存できないエージェントです: {type(agent).__name__}")
    is_actor = isinstance(agent, Actor)
    _insert(
        conn,
        "agent",
        {
            "id": agent.id,
            "dramaturgy_id": dramaturgy_id,
            "sort_order": position,
            "kind": kind,
            "name": agent.name,
            "role": agent.role,
            "persona": agent.persona,
            "rules": json.dumps(agent.rules, ensure_ascii=False),
            "prohibitions": json.dumps(agent.prohibitions, ensure_ascii=False),
            "casting_id": agent.casting_id if is_actor else None,
            "voice_name": agent.voice_name if is_actor else None,
            "tts_provider": agent.tts_provider if is_actor else None,
            "tts_model": agent.tts_model if is_actor else None,
        },
    )
    for order, voice in enumerate(agent.voices if is_actor else []):
        _insert(
            conn,
            "agent_voice",
            {
                "agent_id": agent.id,
                "sort_order": order,
                "language": voice.language,
                "voice_name": voice.voice_name,
                "tts_provider": voice.tts_provider,
                "tts_model": voice.tts_model,
            },
        )
    for order, task in enumerate(agent.tasks):
        _insert(
            conn,
            "agent_task",
            {
                "agent_id": agent.id,
                "sort_order": order,
                "code": task.code,
                "title": task.title,
                "description": task.description,
                "rules": json.dumps(task.rules, ensure_ascii=False),
                "prohibitions": json.dumps(task.prohibitions, ensure_ascii=False),
            },
        )


def _read_agents(conn: sqlite3.Connection, dramaturgy_id: str) -> list[BaseAgent]:
    agents: list[BaseAgent] = []
    for row in _rows(
        conn, "SELECT * FROM agent WHERE dramaturgy_id = ? ORDER BY sort_order", dramaturgy_id
    ):
        tasks = [
            AgentTask(
                task["code"],
                task["title"],
                task["description"],
                json.loads(task["rules"]),
                json.loads(task["prohibitions"]),
            )
            for task in _rows(
                conn, "SELECT * FROM agent_task WHERE agent_id = ? ORDER BY sort_order", row["id"]
            )
        ]
        common = (
            row["role"],
            row["persona"],
            json.loads(row["rules"]),
            json.loads(row["prohibitions"]),
            tasks,
        )
        if row["kind"] == "actor":
            agent = build_actor(
                row["casting_id"],
                row["name"],
                row["voice_name"],
                row["tts_provider"],
                row["tts_model"],
                *common,
                [
                    LanguageVoice(v["language"], v["voice_name"], v["tts_provider"], v["tts_model"])
                    for v in _rows(
                        conn, "SELECT * FROM agent_voice WHERE agent_id = ? ORDER BY sort_order", row["id"]
                    )
                ],
                id=row["id"],
            )
        else:
            agent = build_agent(row["kind"], row["name"], *common, id=row["id"])
        agents.append(agent)
    return agents


def _read_proposal(conn: sqlite3.Connection, dramaturgy_id: str) -> Proposal:
    rows = _rows(conn, "SELECT * FROM proposal WHERE dramaturgy_id = ?", dramaturgy_id)
    if not rows:
        return Proposal()
    row = rows[0]
    characters = [
        ProposalCharacter(item["name"], item["description"])
        for item in _rows(
            conn,
            "SELECT * FROM proposal_character WHERE dramaturgy_id = ? ORDER BY sort_order",
            dramaturgy_id,
        )
    ]
    return Proposal(
        row["title"],
        row["catchphrase"],
        row["logline"],
        row["intent"],
        row["target_area"],
        row["synopsis"],
        characters,
    )


def read_model(conn: sqlite3.Connection) -> ModelDefinition:
    """正本から、プロジェクトの作品モデル全体を組み立てる(組み立てはcore.model.drama.factory)。"""
    nodes = {
        row["id"]: build_temporal_node(
            row["label"], row["date_type"], row["string_date"], id=row["id"]
        )
        for row in _rows(conn, "SELECT * FROM temporal_node ORDER BY rowid")
    }
    locations = {
        row["id"]: build_location(
            row["name"],
            decode_geometry(row["geom"]),
            row["address"],
            row["instruction"],
            row["description"],
            id=row["id"],
        )
        for row in _rows(conn, "SELECT * FROM location ORDER BY fid")
    }
    site_flows = {
        row["id"]: build_site_flow(
            locations[row["origin_id"]],
            locations[row["destination_id"]],
            row["direction"],
            decode_geometry(row["geom"]),
            row["name"],
            id=row["id"],
        )
        for row in _rows(conn, "SELECT * FROM site_flow ORDER BY fid")
    }

    endings = _grouped(
        _rows(conn, "SELECT * FROM sentence_ending ORDER BY character_id, sort_order"),
        "character_id",
    )
    features = _grouped(
        _rows(
            conn,
            "SELECT *, character_id || ':' || characteristic_order AS owner "
            "FROM additional_feature ORDER BY character_id, characteristic_order, sort_order",
        ),
        "owner",
    )
    characteristics = _grouped(
        _rows(conn, "SELECT * FROM characteristic ORDER BY character_id, sort_order"),
        "character_id",
    )
    characters: dict[str, Character] = {}
    for row in _rows(conn, "SELECT * FROM character ORDER BY rowid"):
        characters[row["id"]] = build_character(
            row["name"],
            row["reading"],
            row["gender"],
            row["age"],
            SpeechStyle(
                row["speech_first_person"],
                row["speech_tone"],
                [
                    SentenceEnding(
                        SentenceEndingKind(ending["kind"]),
                        json.loads(ending["examples"]),
                        ending["description"],
                    )
                    for ending in endings.get(row["id"], [])
                ],
                row["speech_description"],
            ),
            [
                Characteristic(
                    characteristic["item"],
                    characteristic["definition"],
                    characteristic["description"],
                    [
                        AdditionalFeature(
                            feature["item"],
                            feature["value"],
                            feature["definition"],
                            feature["description"],
                        )
                        for feature in features.get(
                            f"{row['id']}:{characteristic['sort_order']}", []
                        )
                    ],
                )
                for characteristic in characteristics.get(row["id"], [])
            ],
            id=row["id"],
        )

    members = _grouped(
        _rows(conn, "SELECT * FROM character_group_member ORDER BY sort_order"),
        "character_group_id",
    )
    character_groups = [
        build_character_group(
            row["name"],
            row["kind"],
            [characters[member["character_id"]] for member in members.get(row["id"], [])],
            row["description"],
            id=row["id"],
        )
        for row in _rows(conn, "SELECT * FROM character_group ORDER BY rowid")
    ]

    relationships: dict[str, Relationship] = {}
    for row in _rows(conn, "SELECT * FROM relationship ORDER BY rowid"):
        relationships[row["id"]] = build_relationship(
            characters[row["source_id"]],
            characters[row["target_id"]],
            row["label"],
            nodes[row["period_id"]] if row["period_id"] else None,
            row["description"],
            row["form_of_address"],
            row["tone"],
            id=row["id"],
        )

    involved = _grouped(
        _rows(conn, "SELECT * FROM biography_relationship ORDER BY sort_order"), "biography_id"
    )
    for row in _rows(conn, "SELECT * FROM biography ORDER BY character_id, sort_order"):
        characters[row["character_id"]].biographies.append(
            build_biography(
                nodes[row["period_id"]],
                row["episode"],
                [relationships[item["relationship_id"]] for item in involved.get(row["id"], [])],
                id=row["id"],
            )
        )

    dramaturgies = [
        _read_dramaturgy(conn, row, characters, relationships, nodes, locations, site_flows)
        for row in _rows(conn, "SELECT * FROM dramaturgy ORDER BY sort_order")
    ]
    return ModelDefinition(
        dramaturgies,
        list(characters.values()),
        list(relationships.values()),
        character_groups,
        list(nodes.values()),
        list(locations.values()),
        list(site_flows.values()),
    )


def _read_dramaturgy(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    characters: dict[str, Character],
    relationships: dict[str, Relationship],
    nodes: dict[str, TemporalNode],
    locations: dict[str, Any],
    site_flows: dict[str, Any],
) -> Dramaturgy:
    dramaturgy_id = row["id"]
    history = History(
        [
            build_temporal_edge(
                nodes[edge["source_id"]],
                nodes[edge["target_id"]],
                edge["kind"],
                edge["label"],
                id=edge["id"],
            )
            for edge in _rows(
                conn,
                "SELECT * FROM temporal_edge WHERE dramaturgy_id = ? ORDER BY sort_order",
                dramaturgy_id,
            )
        ]
    )
    casts = {
        cast["id"]: build_cast(
            characters[cast["character_id"]],
            Performance(
                cast["performance_title"],
                cast["performance_description"],
                cast["performance_pace"],
            ),
            cast["voice_gender"],
            cast["language"],
            cast["accent"],
            cast["billing"],
            id=cast["id"],
        )
        for cast in _rows(
            conn,
            'SELECT * FROM "cast" WHERE dramaturgy_id = ? ORDER BY sort_order',
            dramaturgy_id,
        )
    }
    acts = []
    for act in _rows(
        conn,
        "SELECT * FROM act WHERE dramaturgy_id = ? ORDER BY sort_order, rowid",
        dramaturgy_id,
    ):
        scenes = []
        for scene in _rows(
            conn, "SELECT * FROM scene WHERE act_id = ? ORDER BY sort_order, rowid", act["id"]
        ):
            lines = [
                build_line(line["sort_order"], casts[line["cast_id"]], line["text"], id=line["id"])
                for line in _rows(
                    conn,
                    "SELECT * FROM line WHERE scene_id = ? ORDER BY sort_order, rowid",
                    scene["id"],
                )
            ]
            elements = [
                _read_element(conn, element, locations)
                for element in _rows(
                    conn,
                    "SELECT * FROM script_element WHERE scene_id = ? ORDER BY sort_order, rowid",
                    scene["id"],
                )
            ]
            scenes.append(
                build_scene(
                    scene["sort_order"],
                    scene["title"],
                    scene["synopsis"],
                    nodes[scene["period_id"]] if scene["period_id"] else None,
                    locations[scene["location_id"]] if scene["location_id"] else None,
                    _situation(scene, locations),
                    Script(lines),
                    elements,
                    id=scene["id"],
                )
            )
        acts.append(
            build_act(act["sort_order"], act["title"], act["synopsis"], scenes, id=act["id"])
        )
    return build_dramaturgy(
        row["title"],
        row["synopsis"],
        row["input_language"],
        row["output_language"],
        Premise(row["premise_text"]),
        [
            characters[item["character_id"]]
            for item in _rows(
                conn,
                "SELECT * FROM dramaturgy_character WHERE dramaturgy_id = ? ORDER BY sort_order",
                dramaturgy_id,
            )
        ],
        [
            relationships[item["relationship_id"]]
            for item in _rows(
                conn,
                "SELECT * FROM dramaturgy_relationship WHERE dramaturgy_id = ? ORDER BY sort_order",
                dramaturgy_id,
            )
        ],
        list(casts.values()),
        acts,
        history,
        _read_proposal(conn, dramaturgy_id),
        _read_agents(conn, dramaturgy_id),
        [
            locations[item["location_id"]]
            for item in _rows(
                conn,
                "SELECT * FROM dramaturgy_location WHERE dramaturgy_id = ? ORDER BY sort_order",
                dramaturgy_id,
            )
        ],
        [
            site_flows[item["site_flow_id"]]
            for item in _rows(
                conn,
                "SELECT * FROM dramaturgy_site_flow WHERE dramaturgy_id = ? ORDER BY sort_order",
                dramaturgy_id,
            )
        ],
        id=dramaturgy_id,
    )


def _read_element(conn: sqlite3.Connection, row: sqlite3.Row, locations: dict[str, Any]) -> ScriptElement:
    if row["kind"] != "dialogue":
        return build_plain_element(row["kind"], row["sort_order"], id=row["id"])
    return build_dialogue(
        row["sort_order"],
        row["line_id"],
        row["cast_id"],
        row["text"],
        row["action"],
        Direction(
            row["direction_style"],
            row["direction_pace"],
            row["direction_dynamics"],
            row["direction_emotion"],
            row["direction_pause_after"],
        ),
        [
            Translation(item["language"], item["text"])
            for item in _rows(
                conn,
                "SELECT * FROM script_element_translation WHERE element_id = ? ORDER BY sort_order",
                row["id"],
            )
        ],
        _situation(row, locations) if row["has_situation"] else None,
        id=row["id"],
    )
