# core/infra/io/model_definition_writer.py
"""
Dramaturgy(core.model.drama)を、model_definition_readerが読めるモデル定義YAML
(core.schema.formats.dramaturgy_definition)へ書き出す。1つのファイルにも、区画ごとの複数のファイル
(SPLIT_FILES。シーンは、プロット・台詞・原稿に分けて、シーンごとに別のファイル)にも書ける。
どちらも、モデルのコンポジションを入れ子で表す。

- 識別子(id)は常に書き、参照もidで書く(読み直しても識別子が変わらない)。keyは書かない。
- 値の無い属性(None)と空の一覧は書かない。
- 所有者を持たない要素(TemporalNode・Location・Relationship)は、作品から辿れるものを書く
  (人物関係は人物から、時期・場所は経歴・人物関係・時間の位相・シーンから)。
"""

import re
from pathlib import Path
from typing import Any, Optional, Union

import yaml

from core.infra.io.model_definition_reader import YAML_SUFFIXES
from core.model.drama import (
    Atmosphere,
    Character,
    Dialogue,
    Dramaturgy,
    Location,
    Music,
    Relationship,
    Scene,
    ScriptElement,
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
    "characters.yaml": ("dramaturgy.characters", "relationships"),
    "casts.yaml": ("dramaturgy.casts",),
    "acts.yaml": ("dramaturgy.acts",),
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


def _ref(entity: Any) -> Optional[str]:
    return entity.id if entity is not None else None


class _Unowned:
    """所有者を持たない要素を、初めて現れた順に、重複なく集める。"""

    def __init__(self):
        self.items: dict[str, Any] = {}

    def add(self, entity: Any) -> None:
        if entity is not None:
            self.items.setdefault(entity.id, entity)


def dramaturgy_to_spec(dramaturgy: Dramaturgy) -> dict[str, Any]:
    """Dramaturgyを、モデル定義YAMLの形の対応表にする。"""
    nodes = _Unowned()
    locations = _Unowned()
    relationships = _Unowned()

    for edge in dramaturgy.history.edges:
        nodes.add(edge.source)
        nodes.add(edge.target)
    for character in dramaturgy.characters:
        for relationship in character.relationships:
            relationships.add(relationship)
        for biography in character.biographies:
            nodes.add(biography.period)
            relationships.add(biography.involved_relationship)
    for relationship in relationships.items.values():
        nodes.add(relationship.period)
    for act in dramaturgy.acts:
        for scene in act.scenes:
            nodes.add(scene.period)
            locations.add(scene.location)

    spec = {
        "protocol_version": PROTOCOL_VERSION,
        "temporal_nodes": [_temporal_node(node) for node in nodes.items.values()],
        "locations": [_location(location) for location in locations.items.values()],
        "relationships": [
            _relationship(relationship) for relationship in relationships.items.values()
        ],
        "dramaturgy": _compact(
            {
                "id": dramaturgy.id,
                "title": dramaturgy.title,
                "synopsis": dramaturgy.synopsis,
                "input_language": dramaturgy.input_language,
                "output_language": dramaturgy.output_language,
                "premise": _compact({"text": dramaturgy.premise.text}),
                "characters": [_character(character) for character in dramaturgy.characters],
                "casts": [
                    _compact(
                        {
                            "id": cast.id,
                            "character": _ref(cast.character),
                            "provider": cast.provider,
                            "voice_name": cast.voice_name,
                            "language": cast.language,
                            "accent": cast.accent,
                            "notes": cast.notes,
                        }
                    )
                    for cast in dramaturgy.casts
                ],
                "acts": [
                    _compact(
                        {
                            "id": act.id,
                            "order": act.order,
                            "title": act.title,
                            "synopsis": act.synopsis,
                            "scenes": [_scene(scene) for scene in act.scenes],
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
                                    "label": edge.label,
                                    "kind": edge.kind.value,
                                    "source": _ref(edge.source),
                                    "target": _ref(edge.target),
                                }
                            )
                            for edge in dramaturgy.history.edges
                        ]
                    }
                ),
            }
        ),
    }
    return _compact(spec)


def _temporal_node(node: TemporalNode) -> dict[str, Any]:
    return _compact(
        {
            "id": node.id,
            "label": node.label,
            "date_type": node.date_type.value if node.date_type is not None else None,
            "string_date": node.string_date,
        }
    )


def _location(location: Location) -> dict[str, Any]:
    return _compact(
        {
            "id": location.id,
            "name": location.name,
            "latitude": location.latitude,
            "longitude": location.longitude,
            "address": location.address,
            "instruction": location.instruction,
            "description": location.description,
        }
    )


def _character(character: Character) -> dict[str, Any]:
    return _compact(
        {
            "id": character.id,
            "name": character.name,
            "reading": character.reading,
            "gender": character.gender,
            "age": character.age,
            "speech_style": character.speech_style,
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
                        "period": _ref(biography.period),
                        "episode": biography.episode,
                        "involved_relationship": _ref(biography.involved_relationship),
                    }
                )
                for biography in character.biographies
            ],
        }
    )


def _relationship(relationship: Relationship) -> dict[str, Any]:
    return _compact(
        {
            "id": relationship.id,
            "source": _ref(relationship.source),
            "target": _ref(relationship.target),
            "label": relationship.label,
            "period": _ref(relationship.period),
            "description": relationship.description,
        }
    )


def _scene(scene: Scene) -> dict[str, Any]:
    return _compact(
        {
            "id": scene.id,
            "order": scene.order,
            "title": scene.title,
            "synopsis": scene.synopsis,
            "period": _ref(scene.period),
            "location": _ref(scene.location),
            "script": _compact(
                {
                    "lines": [
                        {
                            "id": line.id,
                            "order": line.order,
                            "cast": _ref(line.cast),
                            "text": line.text,
                        }
                        for line in scene.script.lines
                    ]
                }
            ),
            "elements": [_script_element(element) for element in scene.elements],
        }
    )


def _script_element(element: ScriptElement) -> dict[str, Any]:
    if isinstance(element, Dialogue):
        direction = element.direction
        return _compact(
            {
                "type": "dialogue",
                "id": element.id,
                "order": element.order,
                "line": element.line_id,
                "cast": element.cast_id,
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
            }
        )
    if type(element) not in _PLAIN_ELEMENT_TYPES:
        raise ValueError(f"モデル定義YAMLに書けない原稿の要素です: {type(element).__name__}")
    return {"type": _PLAIN_ELEMENT_TYPES[type(element)], "id": element.id, "order": element.order}


class _Dumper(yaml.SafeDumper):
    """複数行の文字列を、読みやすいブロックの形(|)で書く。"""


def _represent_str(dumper: yaml.SafeDumper, value: str) -> yaml.Node:
    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_Dumper.add_representer(str, _represent_str)


def _dump(values: dict[str, Any]) -> str:
    return yaml.dump(
        values, Dumper=_Dumper, allow_unicode=True, sort_keys=False, default_flow_style=False
    )


def dramaturgy_to_yaml(dramaturgy: Dramaturgy) -> str:
    """1つのファイルに書くモデル定義YAMLの文字列。"""
    return _dump(dramaturgy_to_spec(dramaturgy))


def scene_filename(act_index: int, scene_index: int, directory: str) -> str:
    """分割して書くときの、シーンごとのファイル名(幕・シーンの並びの位置。0から)。directoryはPLOT_DIR・SCRIPT_DIR・SCENE_DIR。"""
    return f"{directory}/act_{act_index:03d}_scene_{scene_index:03d}.yaml"


def dramaturgy_to_split_yaml(dramaturgy: Dramaturgy) -> dict[str, str]:
    """
    区画ごとに分けたモデル定義YAML(ファイル名→文字列)。SPLIT_FILESのすべてのファイルと、シーンごとの
    プロット(PLOT_DIR)・台詞(SCRIPT_DIR)・原稿(SCENE_DIR)のファイル(台詞・原稿は、あるときだけ)。どのファイルも
    1ファイルのときと同じ入れ子の形で、その一部だけを持つ。シーンごとのファイルは、属する幕・シーンをidで示す。
    """
    rest = dramaturgy_to_spec(dramaturgy)
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
                values = values if directory == PLOT_DIR else {"id": scene["id"], **values}
                scene_parts[scene_filename(act_index, scene_index, directory)] = {
                    "dramaturgy": {"acts": [{"id": act["id"], "scenes": [values]}]}
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


def write_dramaturgy(dramaturgy: Dramaturgy, path: Union[str, Path]) -> None:
    """1つのファイルに書く(あれば上書き)。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dramaturgy_to_yaml(dramaturgy), encoding="utf-8")


def write_split_dramaturgy(dramaturgy: Dramaturgy, directory: Union[str, Path]) -> list[Path]:
    """
    ディレクトリに区画ごとのファイル(SPLIT_FILES)と、シーンごとのプロット・台詞・原稿のファイルを書き、書いたファイルを返す(あれば上書き)。
    読むときはディレクトリの中のYAMLをすべて重ね合わせるので:
    - 前に書いたシーンごとのファイル(プロット・台詞・原稿)で、今回書かないもの(シーンが減った等)は消す。
    - それ以外のYAML(このモジュールが書く名前でないもの)があれば、何も書かずにValueError。
    """
    directory = Path(directory)
    texts = dramaturgy_to_split_yaml(dramaturgy)
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
