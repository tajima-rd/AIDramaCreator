# core/infra/io/model_definition_writer.py
"""
Dramaturgy(core.model.drama)を、model_definition_readerが読めるモデル定義YAML
(core.schema.formats.dramaturgy_definition)へ書き出す。1つのファイルにも、区画ごとの複数のファイル
(SPLIT_FILES。シーンは、プロット・台詞・原稿に分けて、シーンごとに別のファイル)にも書ける。
どちらも、モデルのコンポジションを入れ子で表す。

- すべてのエンティティにid(識別子。読み直しても変わらない)とkey(種類と通し番号。書き出すたびに振る)を書き、
  参照は{ref: key}で書く(core.schema.formats.dramaturgy_definition「識別子と参照」)。
- 値の無い属性(None)と空の一覧は書かない。
- 所有者を持たない要素(TemporalNode・Location・Relationship)は、作品から辿れるものを書く
  (人物関係は人物から、時期・場所は経歴・人物関係・時間の位相・シーンから)。
"""

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Optional, Union

import yaml

from core.infra.io.model_definition_reader import YAML_SUFFIXES, ModelDefinition
from core.model.agent import Actor, BaseAgent
from core.model.agent.factory import AGENT_ROLES
from core.model.drama import (
    Atmosphere,
    Character,
    CharacterGroup,
    Dialogue,
    Dramaturgy,
    Location,
    Music,
    Proposal,
    Relationship,
    Scene,
    ScriptElement,
    Situation,
    SoundEffect,
    TemporalNode,
)
from core.schema.formats.dramaturgy_definition import PROTOCOL_VERSION

# 分割して書くときのファイル名→そのファイルに書く部分(入れ子の道筋。"dramaturgy.characters"はdramaturgyの中の
# characters)。どのファイルにも割り当てない部分(dramaturgyの題・あらすじ等)は、先頭のファイルに書く
SPLIT_FILES: dict[str, tuple[str, ...]] = {
    "dramaturgy.yaml": (),
    "temporal.yaml": ("temporal_nodes", "dramaturgy.history"),
    "locations.yaml": ("locations",),
    "characters.yaml": ("characters", "character_groups", "relationships"),
    "casts.yaml": ("dramaturgy.casts",),
    "acts.yaml": ("dramaturgy.acts",),
    "agents.yaml": ("dramaturgy.agents",),
}

# 分割して書くとき、シーンを制作の段階ごとに分けて、シーンごとに1つずつ書くファイルを置くディレクトリ
# (旧来のplot/・script/・scene/に対応する)
PLOT_DIR = "plots"  # プロット: シーンの題・あらすじ・時期・場所(台詞・原稿を除いたシーン)
SCRIPT_DIR = "scripts"  # 台詞(Scene.script)
SCENE_DIR = "scenes"  # 演出付きの原稿(Scene.elements)

# 固有の属性を持たない原稿の要素のクラス→モデル定義YAMLのtype
_PLAIN_ELEMENT_TYPES: dict[type[ScriptElement], str] = {
    SoundEffect: "sound_effect",
    Atmosphere: "atmosphere",
    Music: "music",
}


def _compact(values: dict[str, Any]) -> dict[str, Any]:
    """Noneと空の一覧・対応表を除く。"""
    return {
        key: value
        for key, value in values.items()
        if value is not None and value != [] and value != {}
    }


class _Unowned:
    """所有者を持たない要素を、初めて現れた順に、重複なく集める。"""

    def __init__(self):
        self.items: dict[str, Any] = {}

    def add(self, entity: Any) -> None:
        if entity is not None:
            self.items.setdefault(entity.id, entity)


class _Keys:
    """書き出すエンティティのkey(種類と通し番号。character_001等)。idから引く。"""

    def __init__(self):
        self._by_id: dict[str, str] = {}
        self._counts: dict[str, int] = {}

    def assign(self, kind: str, entity: Any, prefix: Optional[str] = None) -> str:
        """entityにkeyを付ける(付いていればそれを返す)。prefixを渡すと、その下の通し番号(scene_001_line_001)。"""
        if entity.id not in self._by_id:
            name = f"{prefix}_{kind}" if prefix else kind
            self._counts[name] = self._counts.get(name, 0) + 1
            self._by_id[entity.id] = f"{name}_{self._counts[name]:03d}"
        return self._by_id[entity.id]

    def ref(self, entity_or_id: Any) -> Optional[dict[str, str]]:
        """参照({ref: key})。entityかidを受ける。"""
        if entity_or_id is None:
            return None
        entity_id = entity_or_id if isinstance(entity_or_id, str) else entity_or_id.id
        if entity_id not in self._by_id:
            raise ValueError(f"参照先(id '{entity_id}')が、書き出すモデル定義の中にありません")
        return {"ref": self._by_id[entity_id]}


def dramaturgy_to_spec(
    dramaturgy: Dramaturgy,
    characters: Optional[Sequence[Character]] = None,
    relationships: Optional[Sequence[Relationship]] = None,
    character_groups: Sequence[CharacterGroup] = (),
) -> dict[str, Any]:
    """
    Dramaturgyを、モデル定義YAMLの形の対応表にする。すべてのエンティティにidとkey(種類と通し番号)を書き、
    参照は{ref: key}で書く。keyは書き出すたびに振り直す(モデルに残らないため)。
    characters・relationships・character_groupsは、作品の外(持ち主はProject)にある人物・人物関係・人物のまとまりの一覧
    (ModelDefinitionの同名の属性)。
    省略すれば、作品から辿れるもの(作品・配役の人物、人物と経歴の人物関係)を書く。作品の側には参照の一覧を書く。
    """
    return _to_spec([dramaturgy], characters, relationships, character_groups, (), (), "dramaturgy")


def model_definition_to_spec(definition: ModelDefinition) -> dict[str, Any]:
    """
    ModelDefinition(プロジェクトの作品モデル全体)を、モデル定義YAMLの形の対応表にする。作品はdramaturgiesの一覧に書き
    (作品が1つでも)、時点・場所は辿れないものも含めてすべて書く。DBの版・下書きの写しに使う(docs/architecture.md 7節)。
    """
    return _to_spec(
        definition.dramaturgies,
        definition.characters,
        definition.relationships,
        definition.character_groups,
        definition.temporal_nodes,
        definition.locations,
        "dramaturgies",
    )


def _to_spec(
    dramaturgies: Sequence[Dramaturgy],
    characters: Optional[Sequence[Character]],
    relationships: Optional[Sequence[Relationship]],
    character_groups: Sequence[CharacterGroup],
    temporal_nodes: Sequence[TemporalNode],
    locations: Sequence[Location],
    section: str,
) -> dict[str, Any]:
    """
    作品の一覧をモデル定義YAMLの形にする。sectionが"dramaturgy"なら1つの作品をdramaturgyに、"dramaturgies"なら一覧で書く。
    temporal_nodes・locationsは、作品から辿れなくても書く時点・場所(辿れるものはその後に足す)。
    """
    nodes = _Unowned()
    places = _Unowned()
    owned_characters = _Unowned()
    owned_relationships = _Unowned()
    for node in temporal_nodes:
        nodes.add(node)
    for location in locations:
        places.add(location)
    for dramaturgy in dramaturgies:
        for character in characters if characters is not None else dramaturgy.characters:
            owned_characters.add(character)
        for relationship in (
            relationships if relationships is not None else dramaturgy.relationships
        ):
            owned_relationships.add(relationship)
        for cast in dramaturgy.casts:
            owned_characters.add(cast.character)
    for group in character_groups:
        for member in group.members:
            owned_characters.add(member)

    for dramaturgy in dramaturgies:
        for edge in dramaturgy.history.edges:
            nodes.add(edge.source)
            nodes.add(edge.target)
    # 参照が切れないよう、人物の人物関係・経歴の人物関係と、人物関係の両端の人物を、増えなくなるまで集める
    while True:
        size = (len(owned_characters.items), len(owned_relationships.items))
        for character in list(owned_characters.items.values()):
            for relationship in character.relationships:
                owned_relationships.add(relationship)
            for biography in character.biographies:
                for relationship in biography.involved_relationships:
                    owned_relationships.add(relationship)
        for relationship in list(owned_relationships.items.values()):
            owned_characters.add(relationship.source)
            owned_characters.add(relationship.target)
        if size == (len(owned_characters.items), len(owned_relationships.items)):
            break
    for character in owned_characters.items.values():
        for biography in character.biographies:
            nodes.add(biography.period)
    for relationship in owned_relationships.items.values():
        nodes.add(relationship.period)
    for dramaturgy in dramaturgies:
        for act in dramaturgy.acts:
            for scene in act.scenes:
                nodes.add(scene.period)
                places.add(scene.location)
                places.add(scene.situation.location)
                for element in scene.elements:
                    if isinstance(element, Dialogue) and element.situation:
                        places.add(element.situation.location)

    # 参照より先に、参照される側のkeyを振る(書く順と同じ順で番号を振る)
    keys = _Keys()
    for dramaturgy in dramaturgies:
        keys.assign("dramaturgy", dramaturgy)
    for node in nodes.items.values():
        keys.assign("temporal_node", node)
    for location in places.items.values():
        keys.assign("location", location)
    for character in owned_characters.items.values():
        keys.assign("character", character)
    for group in character_groups:
        keys.assign("character_group", group)
    for relationship in owned_relationships.items.values():
        keys.assign("relationship", relationship)
    for dramaturgy in dramaturgies:
        for cast in dramaturgy.casts:
            keys.assign("cast", cast)
    for dramaturgy in dramaturgies:
        for act in dramaturgy.acts:
            keys.assign("act", act)
            for scene in act.scenes:
                scene_key = keys.assign("scene", scene)
                for line in scene.script.lines:
                    keys.assign("line", line, prefix=scene_key)

    dramaturgy_specs = [_dramaturgy(dramaturgy, keys) for dramaturgy in dramaturgies]
    spec = {
        "protocol_version": PROTOCOL_VERSION,
        "temporal_nodes": [_temporal_node(node, keys) for node in nodes.items.values()],
        "locations": [_location(location, keys) for location in places.items.values()],
        "characters": [
            _character(character, keys) for character in owned_characters.items.values()
        ],
        "character_groups": [
            _compact(
                {
                    "id": group.id,
                    "key": keys.assign("character_group", group),
                    "name": group.name,
                    "kind": group.kind,
                    "members": [keys.ref(member) for member in group.members],
                    "description": group.description,
                }
            )
            for group in character_groups
        ],
        "relationships": [
            _relationship(relationship, keys) for relationship in owned_relationships.items.values()
        ],
        section: dramaturgy_specs[0] if section == "dramaturgy" else dramaturgy_specs,
    }
    return _compact(spec)


def _proposal(proposal: Proposal) -> dict[str, Any]:
    """企画書(何も書かれていなければ空の対応表になり、_compactで省かれる)。"""
    return _compact(
        {
            "title": proposal.title,
            "catchphrase": proposal.catchphrase,
            "logline": proposal.logline,
            "intent": proposal.intent,
            "target_area": proposal.target_area,
            "synopsis": proposal.synopsis,
            "characters": [
                _compact({"name": c.name, "description": c.description})
                for c in proposal.characters
            ],
        }
    )


def _dramaturgy(dramaturgy: Dramaturgy, keys: _Keys) -> dict[str, Any]:
    return _compact(
        {
            "id": dramaturgy.id,
            "key": keys.assign("dramaturgy", dramaturgy),
            "title": dramaturgy.title,
            "synopsis": dramaturgy.synopsis,
            "input_language": dramaturgy.input_language,
            "output_language": dramaturgy.output_language,
            "premise": _compact({"text": dramaturgy.premise.text}),
            "proposal": _proposal(dramaturgy.proposal),
            "characters": [keys.ref(character) for character in dramaturgy.characters],
            "relationships": [keys.ref(relationship) for relationship in dramaturgy.relationships],
            "casts": [
                _compact(
                    {
                        "id": cast.id,
                        "key": keys.assign("cast", cast),
                        "character": keys.ref(cast.character),
                        "performance": _compact(
                            {
                                "title": cast.performance.title,
                                "description": cast.performance.description,
                                "pace": cast.performance.pace,
                            }
                        ),
                        "voice_gender": cast.voice_gender.value if cast.voice_gender else None,
                        "language": cast.language,
                        "accent": cast.accent,
                    }
                )
                for cast in dramaturgy.casts
            ],
            "acts": [
                _compact(
                    {
                        "id": act.id,
                        "key": keys.assign("act", act),
                        "order": act.order,
                        "title": act.title,
                        "synopsis": act.synopsis,
                        "scenes": [_scene(scene, keys) for scene in act.scenes],
                    }
                )
                for act in dramaturgy.acts
            ],
            "history": _compact(
                {
                    "edges": [
                        _compact(
                            {
                                "id": edge.id,
                                "key": keys.assign("temporal_edge", edge),
                                "label": edge.label,
                                "kind": edge.kind.value,
                                "source": keys.ref(edge.source),
                                "target": keys.ref(edge.target),
                            }
                        )
                        for edge in dramaturgy.history.edges
                    ]
                }
            ),
            "agents": _agents(dramaturgy.agents, keys),
        }
    )


def _agents(agents: Sequence[BaseAgent], keys: _Keys) -> dict[str, Any]:
    """
    エージェントを職能ごとの区画にする(区画名は職能の複数形、keyは職能と通し番号)。Actorの配役は{ref: key}。
    role・rules・prohibitions・タスクは、既定と同じでもすべて書く(作品ごとの全文を残す)。rules・prohibitionsは、
    省略(=既定)と区別するため、空の一覧も書く。
    """
    roles = {cls: role for role, cls in AGENT_ROLES.items()}
    sections: dict[str, list[dict[str, Any]]] = {}
    for agent in agents:
        if isinstance(agent, Actor):
            role = "actor"
        elif type(agent) in roles:
            role = roles[type(agent)]
        else:
            raise ValueError(f"モデル定義YAMLに書けないエージェントです: {type(agent).__name__}")
        values = _compact(
            {
                "id": agent.id,
                "key": keys.assign(role, agent),
                "name": agent.name,
                "role": agent.role,
                "persona": agent.persona,
            }
        )
        values.update({"rules": list(agent.rules), "prohibitions": list(agent.prohibitions)})
        values["tasks"] = [
            {
                **_compact(
                    {"code": task.code, "title": task.title, "description": task.description}
                ),
                "rules": list(task.rules),
                "prohibitions": list(task.prohibitions),
            }
            for task in agent.tasks
        ]
        if isinstance(agent, Actor):
            values.update(
                _compact({"cast": keys.ref(agent.casting_id), "voice_name": agent.voice_name})
            )
        sections.setdefault(f"{role}s", []).append(values)
    return sections


def _temporal_node(node: TemporalNode, keys: _Keys) -> dict[str, Any]:
    return _compact(
        {
            "id": node.id,
            "key": keys.assign("temporal_node", node),
            "label": node.label,
            "date_type": node.date_type.value if node.date_type is not None else None,
            "string_date": node.string_date,
        }
    )


def _location(location: Location, keys: _Keys) -> dict[str, Any]:
    return _compact(
        {
            "id": location.id,
            "key": keys.assign("location", location),
            "name": location.name,
            "latitude": location.latitude,
            "longitude": location.longitude,
            "address": location.address,
            "instruction": location.instruction,
            "description": location.description,
        }
    )


def _character(character: Character, keys: _Keys) -> dict[str, Any]:
    return _compact(
        {
            "id": character.id,
            "key": keys.assign("character", character),
            "name": character.name,
            "reading": character.reading,
            "gender": character.gender,
            "age": character.age,
            "speech_style": _compact(
                {
                    "first_person": character.speech_style.first_person,
                    "tone": character.speech_style.tone,
                    "endings": [
                        _compact(
                            {
                                "kind": ending.kind.value,
                                "examples": ending.examples,
                                "description": ending.description,
                            }
                        )
                        for ending in character.speech_style.endings
                    ],
                    "description": character.speech_style.description,
                }
            ),
            "characteristics": [
                _compact(
                    {
                        "item": characteristic.item,
                        "definition": characteristic.definition,
                        "description": characteristic.description,
                        "features": [
                            _compact(
                                {
                                    "item": feature.item,
                                    "value": feature.value,
                                    "definition": feature.definition,
                                    "description": feature.description,
                                }
                            )
                            for feature in characteristic.features
                        ],
                    }
                )
                for characteristic in character.characteristics
            ],
            "biographies": [
                _compact(
                    {
                        "id": biography.id,
                        "key": keys.assign("biography", biography),
                        "period": keys.ref(biography.period),
                        "episode": biography.episode,
                        "involved_relationships": [
                            keys.ref(relationship)
                            for relationship in biography.involved_relationships
                        ],
                    }
                )
                for biography in character.biographies
            ],
        }
    )


def _relationship(relationship: Relationship, keys: _Keys) -> dict[str, Any]:
    return _compact(
        {
            "id": relationship.id,
            "key": keys.assign("relationship", relationship),
            "source": keys.ref(relationship.source),
            "target": keys.ref(relationship.target),
            "label": relationship.label,
            "period": keys.ref(relationship.period),
            "description": relationship.description,
            "form_of_address": relationship.form_of_address,
            "tone": relationship.tone,
        }
    )


def _situation(situation: Situation, keys: _Keys) -> dict[str, Any]:
    return _compact(
        {
            "location": keys.ref(situation.location),
            "description": situation.description,
            "time_of_day": situation.time_of_day,
            "environment": situation.environment,
        }
    )


def _scene(scene: Scene, keys: _Keys) -> dict[str, Any]:
    scene_key = keys.assign("scene", scene)
    return _compact(
        {
            "id": scene.id,
            "key": scene_key,
            "order": scene.order,
            "title": scene.title,
            "synopsis": scene.synopsis,
            "period": keys.ref(scene.period),
            "location": keys.ref(scene.location),
            "situation": _situation(scene.situation, keys),
            "script": _compact(
                {
                    "lines": [
                        {
                            "id": line.id,
                            "key": keys.assign("line", line, prefix=scene_key),
                            "order": line.order,
                            "cast": keys.ref(line.cast),
                            "text": line.text,
                        }
                        for line in scene.script.lines
                    ]
                }
            ),
            "elements": [_script_element(element, keys, scene_key) for element in scene.elements],
        }
    )


def _script_element(element: ScriptElement, keys: _Keys, scene_key: str) -> dict[str, Any]:
    key = keys.assign("element", element, prefix=scene_key)
    if isinstance(element, Dialogue):
        direction = element.direction
        values = _compact(
            {
                "type": "dialogue",
                "id": element.id,
                "key": key,
                "order": element.order,
                "line": keys.ref(element.line_id),
                "cast": keys.ref(element.cast_id),
                "text": element.text,
                "action": element.action,
                "direction": _compact(
                    {
                        "style": direction.style,
                        "pace": direction.pace,
                        "dynamics": direction.dynamics,
                        "emotion": direction.emotion,
                        "pause_after": direction.pause_after,
                    }
                ),
                "translated_text": element.translated_text,
                "situation": _situation(element.situation, keys) if element.situation else None,
            }
        )
        # 空の状況も書く(省略=シーンの状況と、空の状況を区別する)
        if element.situation is not None and "situation" not in values:
            values["situation"] = {}
        return values
    if type(element) not in _PLAIN_ELEMENT_TYPES:
        raise ValueError(f"モデル定義YAMLに書けない原稿の要素です: {type(element).__name__}")
    return {
        "type": _PLAIN_ELEMENT_TYPES[type(element)],
        "id": element.id,
        "key": key,
        "order": element.order,
    }


class _Dumper(yaml.SafeDumper):
    """複数行の文字列を、読みやすいブロックの形(|)で書く。"""


def _represent_str(dumper: yaml.SafeDumper, value: str) -> yaml.Node:
    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


def _represent_dict(dumper: yaml.SafeDumper, value: dict) -> yaml.Node:
    # 参照({ref: key})は1行で書く
    flow = set(value) == {"ref"}
    return dumper.represent_mapping("tag:yaml.org,2002:map", value, flow_style=flow or None)


_Dumper.add_representer(str, _represent_str)
_Dumper.add_representer(dict, _represent_dict)


def dump_model_definition(values: dict[str, Any]) -> str:
    """モデル定義YAMLの形の対応表を、書き出しと同じ書式(複数行はブロック、参照は1行)の文字列にする。"""
    return _dump(values)


def _dump(values: dict[str, Any]) -> str:
    return yaml.dump(
        values, Dumper=_Dumper, allow_unicode=True, sort_keys=False, default_flow_style=False
    )


def dramaturgy_to_yaml(
    dramaturgy: Dramaturgy,
    characters: Optional[Sequence[Character]] = None,
    relationships: Optional[Sequence[Relationship]] = None,
    character_groups: Sequence[CharacterGroup] = (),
) -> str:
    """1つのファイルに書くモデル定義YAMLの文字列。引数の意味はdramaturgy_to_specと同じ。"""
    return _dump(dramaturgy_to_spec(dramaturgy, characters, relationships, character_groups))


def model_definition_to_yaml(definition: ModelDefinition) -> str:
    """プロジェクトの作品モデル全体を、1つのモデル定義YAMLの文字列にする(model_definition_to_spec)。"""
    return _dump(model_definition_to_spec(definition))


def scene_filename(act_index: int, scene_index: int, directory: str) -> str:
    """分割して書くときの、シーンごとのファイル名(幕・シーンの並びの位置。0から)。directoryはPLOT_DIR・SCRIPT_DIR・SCENE_DIR。"""
    return f"{directory}/act_{act_index:03d}_scene_{scene_index:03d}.yaml"


def dramaturgy_to_split_yaml(
    dramaturgy: Dramaturgy,
    characters: Optional[Sequence[Character]] = None,
    relationships: Optional[Sequence[Relationship]] = None,
    character_groups: Sequence[CharacterGroup] = (),
) -> dict[str, str]:
    """
    区画ごとに分けたモデル定義YAML(ファイル名→文字列)。SPLIT_FILESのすべてのファイルと、シーンごとの
    プロット(PLOT_DIR)・台詞(SCRIPT_DIR)・原稿(SCENE_DIR)のファイル(台詞・原稿は、あるときだけ)。どのファイルも
    1ファイルのときと同じ入れ子の形で、その一部だけを持つ。シーンごとのファイルは、属する幕・シーンをidとkeyで示す。
    """
    rest = dramaturgy_to_spec(dramaturgy, characters, relationships, character_groups)
    scene_parts: dict[str, dict[str, Any]] = {}
    for act_index, act in enumerate(rest["dramaturgy"].get("acts", [])):
        for scene_index, scene in enumerate(act.pop("scenes", [])):
            stages = {
                SCRIPT_DIR: {"script": scene.pop("script")} if "script" in scene else None,
                SCENE_DIR: {"elements": scene.pop("elements")} if "elements" in scene else None,
                PLOT_DIR: scene,  # 台詞・原稿を除いた残り
            }
            for directory, values in stages.items():
                if values is None:
                    continue
                values = (
                    values
                    if directory == PLOT_DIR
                    else {"id": scene["id"], "key": scene["key"], **values}
                )
                scene_parts[scene_filename(act_index, scene_index, directory)] = {
                    "dramaturgy": {
                        "acts": [{"id": act["id"], "key": act["key"], "scenes": [values]}]
                    }
                }
    parts: dict[str, dict[str, Any]] = {}
    for filename, paths in SPLIT_FILES.items():
        part: dict[str, Any] = {}
        for path in paths:
            *parents, leaf = path.split(".")
            source, target = rest, part
            for parent in parents:
                source = source.get(parent, {})
                target = target.setdefault(parent, {})
            if leaf in source:
                target[leaf] = source.pop(leaf)
        parts[filename] = _compact(part)
    # どのファイルにも割り当てなかった部分は、先頭のファイルへ
    parts[next(iter(SPLIT_FILES))] = rest
    parts.update(scene_parts)
    return {filename: _dump(part) for filename, part in parts.items()}


def _is_scene_file(relative_path: str) -> bool:
    pattern = rf"({PLOT_DIR}|{SCRIPT_DIR}|{SCENE_DIR})/act_\d{{3}}_scene_\d{{3}}\.yaml"
    return re.fullmatch(pattern, relative_path) is not None


def write_dramaturgy(
    dramaturgy: Dramaturgy,
    path: Union[str, Path],
    characters: Optional[Sequence[Character]] = None,
    relationships: Optional[Sequence[Relationship]] = None,
    character_groups: Sequence[CharacterGroup] = (),
) -> None:
    """1つのファイルに書く(あれば上書き)。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        dramaturgy_to_yaml(dramaturgy, characters, relationships, character_groups),
        encoding="utf-8",
    )


def write_split_dramaturgy(
    dramaturgy: Dramaturgy,
    directory: Union[str, Path],
    characters: Optional[Sequence[Character]] = None,
    relationships: Optional[Sequence[Relationship]] = None,
    character_groups: Sequence[CharacterGroup] = (),
) -> list[Path]:
    """
    ディレクトリに区画ごとのファイル(SPLIT_FILES)と、シーンごとのプロット・台詞・原稿のファイルを書き、書いたファイルを返す(あれば上書き)。
    読むときはディレクトリの中のYAMLをすべて重ね合わせるので:
    - 前に書いたシーンごとのファイル(プロット・台詞・原稿)で、今回書かないもの(シーンが減った等)は消す。
    - それ以外のYAML(このモジュールが書く名前でないもの)があれば、何も書かずにValueError。
    """
    directory = Path(directory)
    texts = dramaturgy_to_split_yaml(dramaturgy, characters, relationships, character_groups)
    stale: list[Path] = []
    if directory.is_dir():
        others = []
        for file in sorted(directory.rglob("*")):
            if not (file.is_file() and file.suffix in YAML_SUFFIXES):
                continue
            relative = file.relative_to(directory).as_posix()
            if relative in texts or relative in SPLIT_FILES:
                continue
            if _is_scene_file(relative):
                stale.append(file)
            else:
                others.append(relative)
        if others:
            raise ValueError(
                f"ほかのYAMLがあるディレクトリには書けません({', '.join(others)}): {directory}"
            )
    for file in stale:
        file.unlink()
    written = []
    for filename, text in texts.items():
        file = directory / filename
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text, encoding="utf-8")
        written.append(file)
    return written
