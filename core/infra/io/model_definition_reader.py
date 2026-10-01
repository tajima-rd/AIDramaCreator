# core/infra/io/model_definition_reader.py
"""
モデル定義YAML(core.schema.formats.dramaturgy_definition)から、Dramaturgy(core.model.drama)を組み立てる。
組み立ての規則はcore.model.drama.factoryを使う。書き出しはmodel_definition_writer。

1つのファイルでも、区画ごとに分けた複数のファイル(ディレクトリ)でも読める。1つのファイルに`---`で区切った
複数の文書があってもよい。すべての文書を1つの定義に重ね合わせてから(merge_documents)、形を検証して組み立てる。

参照(key・id)の解決はここで行う。参照先が無い・同じkeyやidが同じ種類に2つある場合はValueError。
"""

from pathlib import Path
from typing import Any, Optional, Union

import yaml

from core.model.drama import (
    AdditionalFeature,
    Character,
    Characteristic,
    Dramaturgy,
    History,
    Premise,
    Scene,
    Script,
)
from core.model.drama.factory import (
    build_act,
    build_biography,
    build_cast,
    build_character,
    build_dialogue,
    build_dramaturgy,
    build_line,
    build_location,
    build_plain_element,
    build_relationship,
    build_scene,
    build_temporal_edge,
    build_temporal_node,
)
from core.model.drama.script_element import Direction
from core.schema.formats.dramaturgy_definition import (
    CharacteristicSpec,
    DialogueSpec,
    DramaturgyDefinition,
    SceneSpec,
)

YAML_SUFFIXES = (".yaml", ".yml")


def merge_documents(documents: list[dict[str, Any]]) -> dict[str, Any]:
    """
    分割して書いたモデル定義YAMLの文書を重ね合わせる。対応表は同じキーどうしを重ね、一覧はidかkeyが同じ
    要素どうしを重ね、それ以外の要素は読んだ順につなげる(シーンを幕とは別のファイルに書ける)。
    同じ場所に異なる値(文字列・数値等)があればValueError。
    """
    merged: dict[str, Any] = {}
    for document in documents:
        if document is None:
            continue
        if not isinstance(document, dict):
            raise ValueError("モデル定義YAMLの文書は、区画名をキーにした対応表でなければなりません")
        _overlay(merged, document, "")
    return merged


def _overlay(merged: dict[str, Any], document: dict[str, Any], path: str) -> None:
    for key, value in document.items():
        where = f"{path}.{key}" if path else str(key)
        if value is None:
            continue
        if key not in merged:
            merged[key] = value
        elif isinstance(merged[key], dict) and isinstance(value, dict):
            _overlay(merged[key], value, where)
        elif isinstance(merged[key], list) and isinstance(value, list):
            merged[key] = _overlay_list(merged[key], value, where)
        elif merged[key] != value:
            raise ValueError(
                f"'{where}' の値が文書によって食い違っています({merged[key]!r} と {value!r})"
            )


def _overlay_list(merged: list[Any], items: list[Any], path: str) -> list[Any]:
    """一覧を重ねる。idかkeyが同じ要素(対応表)どうしは重ね、それ以外は後ろにつなげる。"""
    result = list(merged)
    for item in items:
        same = _same_item(result, item)
        if same is None:
            result.append(item)
        else:
            _overlay(same, item, f"{path}[{item.get('id') or item.get('key')}]")
    return result


def _same_item(items: list[Any], item: Any) -> Optional[dict[str, Any]]:
    if not isinstance(item, dict):
        return None
    for existing in items:
        if not isinstance(existing, dict):
            continue
        for name in ("id", "key"):
            if item.get(name) is not None and item.get(name) == existing.get(name):
                return existing
    return None


def load_documents(yaml_text: str) -> list[dict[str, Any]]:
    """1つのYAMLの文字列から、`---`で区切った文書をすべて読む。"""
    return list(yaml.safe_load_all(yaml_text))


def definition_files(path: Union[str, Path]) -> list[Path]:
    """読むファイルの一覧。pathがファイルならそれだけ、ディレクトリなら配下のYAMLをすべて(相対パスの名前順)。"""
    path = Path(path)
    if path.is_dir():
        files = sorted(p for p in path.rglob("*") if p.is_file() and p.suffix in YAML_SUFFIXES)
        if not files:
            raise FileNotFoundError(f"モデル定義YAMLがありません: {path}")
        return files
    if not path.is_file():
        raise FileNotFoundError(f"モデル定義YAMLがありません: {path}")
    return [path]


def read_spec(path: Union[str, Path]) -> dict[str, Any]:
    """ファイルかディレクトリから、重ね合わせた後の定義(検証前の対応表)を読む。"""
    documents: list[dict[str, Any]] = []
    for file in definition_files(path):
        documents.extend(load_documents(file.read_text(encoding="utf-8")))
    return merge_documents(documents)


def read_dramaturgy(path: Union[str, Path]) -> Dramaturgy:
    """モデル定義YAMLのファイル、または分割したファイルを置いたディレクトリから、Dramaturgyを組み立てる。"""
    return build_dramaturgy_from_spec(read_spec(path))


def build_dramaturgy_from_yaml(*yaml_texts: str) -> Dramaturgy:
    """モデル定義YAMLの文字列(分割したものは複数)から、Dramaturgyを組み立てる。"""
    documents: list[dict[str, Any]] = []
    for text in yaml_texts:
        documents.extend(load_documents(text))
    return build_dramaturgy_from_spec(merge_documents(documents))


class _References:
    """参照の名前(keyとid)→エンティティの表。参照先は種類(kind)ごとに探す。"""

    def __init__(self):
        self._tables: dict[str, dict[str, Any]] = {}

    def register(self, kind: str, key: Optional[str], entity: Any) -> None:
        table = self._tables.setdefault(kind, {})
        for name in (key, entity.id):
            if name is None:
                continue
            if name in table and table[name] is not entity:
                raise ValueError(f"{kind}の '{name}' が2つあります(keyとidは種類ごとに一意)")
            table[name] = entity

    def resolve(self, kind: str, ref: Optional[str], where: str) -> Any:
        if ref is None:
            return None
        try:
            return self._tables.get(kind, {})[ref]
        except KeyError:
            raise ValueError(f"{where}が参照する{kind} '{ref}' がありません") from None


def build_dramaturgy_from_spec(spec: dict[str, Any]) -> Dramaturgy:
    """
    重ね合わせた後の定義(対応表)の形を検証し、Dramaturgyを組み立てる。参照先の多いものから順に組み立てる:
    時点・場所 → 人物 → 人物関係 → 経歴 → 時間の位相 → 配役 → 幕・シーン・台詞 → 演出付きの原稿。
    """
    definition = DramaturgyDefinition.model_validate(spec)
    dramaturgy_spec = definition.dramaturgy
    refs = _References()

    for node_spec in definition.temporal_nodes:
        node = build_temporal_node(
            node_spec.label, node_spec.date_type, node_spec.string_date, id=node_spec.id
        )
        refs.register("TemporalNode", node_spec.key, node)

    for location_spec in definition.locations:
        location = build_location(
            location_spec.name,
            location_spec.latitude,
            location_spec.longitude,
            location_spec.address,
            location_spec.instruction,
            location_spec.description,
            id=location_spec.id,
        )
        refs.register("Location", location_spec.key, location)

    characters: list[Character] = []
    for character_spec in dramaturgy_spec.characters:
        character = build_character(
            character_spec.name,
            character_spec.reading,
            character_spec.gender,
            character_spec.age,
            character_spec.speech_style,
            _characteristics(character_spec.characteristics),
            id=character_spec.id,
        )
        refs.register("Character", character_spec.key, character)
        characters.append(character)

    for relationship_spec in definition.relationships:
        where = f"人物関係 '{relationship_spec.label}'"
        relationship = build_relationship(
            refs.resolve("Character", relationship_spec.source, where),
            refs.resolve("Character", relationship_spec.target, where),
            relationship_spec.label,
            refs.resolve("TemporalNode", relationship_spec.period, where),
            relationship_spec.description,
            id=relationship_spec.id,
        )
        refs.register("Relationship", relationship_spec.key, relationship)

    # 経歴は人物関係を参照し、人物関係は人物を参照するので、人物の後で加える
    for character, character_spec in zip(characters, dramaturgy_spec.characters, strict=True):
        where = f"人物 '{character.name}' の経歴"
        for biography_spec in character_spec.biographies:
            character.biographies.append(
                build_biography(
                    refs.resolve("TemporalNode", biography_spec.period, where),
                    biography_spec.episode,
                    refs.resolve("Relationship", biography_spec.involved_relationship, where),
                    id=biography_spec.id,
                )
            )

    history = History()
    for edge_spec in dramaturgy_spec.history.edges if dramaturgy_spec.history else []:
        where = "時間の位相(history.edges)"
        edge = build_temporal_edge(
            refs.resolve("TemporalNode", edge_spec.source, where),
            refs.resolve("TemporalNode", edge_spec.target, where),
            edge_spec.kind,
            edge_spec.label,
            id=edge_spec.id,
        )
        refs.register("TemporalEdge", edge_spec.key, edge)
        history.edges.append(edge)

    casts = []
    for cast_spec in dramaturgy_spec.casts:
        cast = build_cast(
            refs.resolve("Character", cast_spec.character, "配役"),
            cast_spec.provider,
            cast_spec.voice_name,
            cast_spec.language,
            cast_spec.accent,
            cast_spec.notes,
            id=cast_spec.id,
        )
        refs.register("Cast", cast_spec.key, cast)
        casts.append(cast)

    acts = []
    built_scenes: list[tuple[Scene, SceneSpec]] = []
    for act_index, act_spec in enumerate(dramaturgy_spec.acts):
        scenes = []
        for scene_index, scene_spec in enumerate(act_spec.scenes):
            where = f"幕{act_index}のシーン{scene_index}"
            lines = []
            for line_index, line_spec in enumerate(
                scene_spec.script.lines if scene_spec.script else []
            ):
                line = build_line(
                    _order(line_spec.order, line_index),
                    refs.resolve("Cast", line_spec.cast, f"{where}の台詞"),
                    line_spec.text,
                    id=line_spec.id,
                )
                refs.register("Line", line_spec.key, line)
                lines.append(line)
            scene = build_scene(
                _order(scene_spec.order, scene_index),
                scene_spec.title,
                scene_spec.synopsis,
                refs.resolve("TemporalNode", scene_spec.period, where),
                refs.resolve("Location", scene_spec.location, where),
                Script(lines),
                id=scene_spec.id,
            )
            scenes.append(scene)
            built_scenes.append((scene, scene_spec))
        acts.append(
            build_act(
                _order(act_spec.order, act_index),
                act_spec.title,
                act_spec.synopsis,
                scenes,
                id=act_spec.id,
            )
        )

    # 演出付きの原稿は台詞(Line)を参照するので、すべてのシーンの台詞の後で加える
    for scene, scene_spec in built_scenes:
        for element_index, element_spec in enumerate(scene_spec.elements):
            order = _order(element_spec.order, element_index)
            if isinstance(element_spec, DialogueSpec):
                where = f"シーン '{scene.title or scene.order}' の原稿"
                direction = (
                    Direction(**element_spec.direction.model_dump())
                    if element_spec.direction
                    else None
                )
                element = build_dialogue(
                    order,
                    refs.resolve("Line", element_spec.line, where).id,
                    refs.resolve("Cast", element_spec.cast, where).id,
                    element_spec.text,
                    element_spec.action,
                    direction,
                    element_spec.translated_text,
                    id=element_spec.id,
                )
            else:
                element = build_plain_element(element_spec.type, order, id=element_spec.id)
            scene.elements.append(element)

    return build_dramaturgy(
        dramaturgy_spec.title,
        dramaturgy_spec.synopsis,
        dramaturgy_spec.input_language,
        dramaturgy_spec.output_language,
        Premise(dramaturgy_spec.premise.text) if dramaturgy_spec.premise else None,
        characters,
        casts,
        acts,
        history,
        id=dramaturgy_spec.id,
    )


def _characteristics(specs: list[CharacteristicSpec]) -> list[Characteristic]:
    return [
        Characteristic(
            spec.item,
            spec.definition,
            spec.description,
            [
                AdditionalFeature(f.item, f.value, f.definition, f.description)
                for f in spec.features
            ],
        )
        for spec in specs
    ]


def _order(order: Optional[int], index: int) -> int:
    """orderを省略したら、並びの中の位置(0から)。"""
    return order if order is not None else index
