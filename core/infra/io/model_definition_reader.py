# core/infra/io/model_definition_reader.py
"""
モデル定義YAML(core.schema.formats.dramaturgy_definition)から、Dramaturgy(core.model.drama)と、エージェント
(core.model.agent)を組み立てる(ModelDefinition)。
組み立ての規則はcore.model.drama.factoryを使う。書き出しはmodel_definition_writer。

1つのファイルでも、区画ごとに分けた複数のファイル(ディレクトリ)でも読める。1つのファイルに`---`で区切った
複数の文書があってもよい。すべての文書を1つの定義に重ね合わせてから(merge_documents)、形を検証して組み立てる。

参照({ref: key})の解決はここで行う。参照先のkeyが無い・同じkeyやidが同じ種類に2つある場合はValueError。
"""

from pathlib import Path
from typing import Any, Optional, Union

import yaml

from core.infra.io.agent_default_reader import complete_agent_spec
from core.model.agent import AgentTask, BaseAgent
from core.model.agent.factory import AGENT_ROLES, build_actor, build_agent
from core.model.drama import (
    AdditionalFeature,
    Character,
    CharacterGroup,
    Characteristic,
    Dramaturgy,
    History,
    Location,
    Performance,
    Premise,
    Proposal,
    ProposalCharacter,
    Relationship,
    Scene,
    Script,
    SentenceEnding,
    Situation,
    SpeechStyle,
    TemporalNode,
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
    build_temporal_edge,
    build_temporal_node,
)
from core.model.drama.script_element import Direction
from core.schema.formats.dramaturgy_definition import (
    AgentSpec,
    AgentsSpec,
    CharacteristicSpec,
    DialogueSpec,
    DramaturgyDefinition,
    DramaturgySpec,
    ProposalSpec,
    Ref,
    SceneSpec,
    SituationSpec,
    SpeechStyleSpec,
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


class ModelDefinition:
    """
    モデル定義YAMLから組み立てたもの。作品(Dramaturgy。複数あり得る。エージェントは作品が所有する)、人物と人物関係、
    所有者を持たない時点・場所。
    人物・人物のまとまり・人物関係・時点・場所の持ち主はProjectだが、Projectの作り直しまでは、ここに仮置きする
    (作品は参照で持つ。2026-10-01ユーザー)。プロジェクトの作品モデル全体(DBの正本。core.infra.store.drama_model_store)もこの形で扱う。
    """

    def __init__(
        self,
        dramaturgies: Optional[list[Dramaturgy]] = None,
        characters: Optional[list[Character]] = None,
        relationships: Optional[list[Relationship]] = None,
        character_groups: Optional[list[CharacterGroup]] = None,
        temporal_nodes: Optional[list[TemporalNode]] = None,
        locations: Optional[list[Location]] = None,
    ):
        self.dramaturgies: list[Dramaturgy] = list(dramaturgies or [])
        self.characters: list[Character] = list(characters or [])
        self.relationships: list[Relationship] = list(relationships or [])
        self.character_groups: list[CharacterGroup] = list(character_groups or [])
        self.temporal_nodes: list[TemporalNode] = list(temporal_nodes or [])
        self.locations: list[Location] = list(locations or [])

    @property
    def dramaturgy(self) -> Dramaturgy:
        """作品が1つのときの、その作品。1つでなければValueError。"""
        if len(self.dramaturgies) != 1:
            raise ValueError(
                f"作品が{len(self.dramaturgies)}個あります(dramaturgyは作品が1つのときだけ使える)"
            )
        return self.dramaturgies[0]


def read_model_definition(path: Union[str, Path]) -> ModelDefinition:
    """モデル定義YAMLのファイル、または分割したファイルを置いたディレクトリから、作品とエージェントを組み立てる。"""
    return build_model_definition_from_spec(read_spec(path))


def build_model_definition_from_yaml(*yaml_texts: str) -> ModelDefinition:
    """モデル定義YAMLの文字列(分割したものは複数)から、作品とエージェントを組み立てる。"""
    documents: list[dict[str, Any]] = []
    for text in yaml_texts:
        documents.extend(load_documents(text))
    return build_model_definition_from_spec(merge_documents(documents))


def read_dramaturgy(path: Union[str, Path]) -> Dramaturgy:
    """read_model_definitionの作品だけ(作品が1つのとき)。"""
    return read_model_definition(path).dramaturgy


def build_dramaturgy_from_yaml(*yaml_texts: str) -> Dramaturgy:
    """build_model_definition_from_yamlの作品だけ。"""
    return build_model_definition_from_yaml(*yaml_texts).dramaturgy


def build_dramaturgy_from_spec(spec: dict[str, Any]) -> Dramaturgy:
    """build_model_definition_from_specの作品だけ。"""
    return build_model_definition_from_spec(spec).dramaturgy


class _References:
    """key→エンティティの表(参照の受け口)と、idの重なりの検査。どちらも種類(kind)ごとに一意。
    参照({ref: key})はkeyだけで解決する(idでは参照しない)。"""

    def __init__(self):
        self._keys: dict[str, dict[str, Any]] = {}
        self._ids: dict[str, set[str]] = {}

    def register(self, kind: str, key: Optional[str], entity: Any) -> None:
        ids = self._ids.setdefault(kind, set())
        if entity.id in ids:
            raise ValueError(f"{kind}のid '{entity.id}' が2つあります(idは種類ごとに一意)")
        ids.add(entity.id)
        if key is not None:
            keys = self._keys.setdefault(kind, {})
            if key in keys:
                raise ValueError(f"{kind}のkey '{key}' が2つあります(keyは種類ごとに一意)")
            keys[key] = entity

    def resolve(self, kind: str, ref: Optional[Ref], where: str) -> Any:
        if ref is None:
            return None
        try:
            return self._keys.get(kind, {})[ref.ref]
        except KeyError:
            raise ValueError(f"{where}が参照する{kind}のkey '{ref.ref}' がありません") from None


def build_model_definition_from_spec(spec: dict[str, Any]) -> ModelDefinition:
    """
    重ね合わせた後の定義(対応表)の形を検証し、作品とエージェントを組み立てる。参照先の多いものから順に組み立てる:
    時点・場所 → 人物 → 人物関係 → 経歴 → 作品ごとに(時間の位相 → 配役 → 幕・シーン・台詞 → 演出付きの原稿 → 作品。
    人物・人物関係は参照) → エージェント。作品はdramaturgy、dramaturgiesの順。
    """
    definition = DramaturgyDefinition.model_validate(spec)
    refs = _References()

    temporal_nodes: list[TemporalNode] = []
    for node_spec in definition.temporal_nodes:
        node = build_temporal_node(
            node_spec.label, node_spec.date_type, node_spec.string_date, id=node_spec.id
        )
        refs.register("TemporalNode", node_spec.key, node)
        temporal_nodes.append(node)

    locations: list[Location] = []
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
        locations.append(location)

    characters: list[Character] = []
    for character_spec in definition.characters:
        character = build_character(
            character_spec.name,
            character_spec.reading,
            character_spec.gender,
            character_spec.age,
            _speech_style(character_spec.speech_style),
            _characteristics(character_spec.characteristics),
            id=character_spec.id,
        )
        refs.register("Character", character_spec.key, character)
        characters.append(character)

    character_groups: list[CharacterGroup] = []
    for group_spec in definition.character_groups:
        group = build_character_group(
            group_spec.name,
            group_spec.kind,
            [
                refs.resolve("Character", ref, f"人物のまとまり '{group_spec.name}'")
                for ref in group_spec.members
            ],
            group_spec.description,
            id=group_spec.id,
        )
        refs.register("CharacterGroup", group_spec.key, group)
        character_groups.append(group)

    relationships: list[Relationship] = []
    for relationship_spec in definition.relationships:
        where = f"人物関係 '{relationship_spec.label}'"
        relationship = build_relationship(
            refs.resolve("Character", relationship_spec.source, where),
            refs.resolve("Character", relationship_spec.target, where),
            relationship_spec.label,
            refs.resolve("TemporalNode", relationship_spec.period, where),
            relationship_spec.description,
            relationship_spec.form_of_address,
            relationship_spec.tone,
            id=relationship_spec.id,
        )
        refs.register("Relationship", relationship_spec.key, relationship)
        relationships.append(relationship)

    # 経歴は人物関係を参照し、人物関係は人物を参照するので、人物の後で加える
    for character, character_spec in zip(characters, definition.characters, strict=True):
        where = f"人物 '{character.name}' の経歴"
        for biography_spec in character_spec.biographies:
            biography = build_biography(
                refs.resolve("TemporalNode", biography_spec.period, where),
                biography_spec.episode,
                [
                    refs.resolve("Relationship", ref, where)
                    for ref in biography_spec.involved_relationships
                ],
                id=biography_spec.id,
            )
            refs.register("Biography", biography_spec.key, biography)
            character.biographies.append(biography)

    dramaturgy_specs = ([definition.dramaturgy] if definition.dramaturgy else []) + list(
        definition.dramaturgies
    )
    dramaturgies = [_dramaturgy(dramaturgy_spec, refs) for dramaturgy_spec in dramaturgy_specs]
    return ModelDefinition(
        dramaturgies,
        characters,
        relationships,
        character_groups,
        temporal_nodes,
        locations,
    )


def _dramaturgy(dramaturgy_spec: DramaturgySpec, refs: "_References") -> Dramaturgy:
    """1つの作品を組み立てる(時間の位相 → 配役 → 幕・シーン・台詞 → 演出付きの原稿 → 作品)。"""
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
            (
                Performance(
                    cast_spec.performance.title,
                    cast_spec.performance.description,
                    cast_spec.performance.pace,
                )
                if cast_spec.performance
                else None
            ),
            cast_spec.voice_gender,
            cast_spec.language,
            cast_spec.accent,
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
                _situation(scene_spec.situation, refs, where),
                Script(lines),
                id=scene_spec.id,
            )
            refs.register("Scene", scene_spec.key, scene)
            scenes.append(scene)
            built_scenes.append((scene, scene_spec))
        act = build_act(
            _order(act_spec.order, act_index),
            act_spec.title,
            act_spec.synopsis,
            scenes,
            id=act_spec.id,
        )
        refs.register("Act", act_spec.key, act)
        acts.append(act)

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
                    (
                        _situation(element_spec.situation, refs, where)
                        if element_spec.situation
                        else None
                    ),
                    id=element_spec.id,
                )
            else:
                element = build_plain_element(element_spec.type, order, id=element_spec.id)
            refs.register("ScriptElement", element_spec.key, element)
            scene.elements.append(element)

    dramaturgy = build_dramaturgy(
        dramaturgy_spec.title,
        dramaturgy_spec.synopsis,
        dramaturgy_spec.input_language,
        dramaturgy_spec.output_language,
        Premise(dramaturgy_spec.premise.text) if dramaturgy_spec.premise else None,
        [refs.resolve("Character", ref, "作品の人物") for ref in dramaturgy_spec.characters],
        [
            refs.resolve("Relationship", ref, "作品の人物関係")
            for ref in dramaturgy_spec.relationships
        ],
        casts,
        acts,
        history,
        _proposal(dramaturgy_spec.proposal),
        _agents(dramaturgy_spec.agents, refs),
        id=dramaturgy_spec.id,
    )
    refs.register("Dramaturgy", dramaturgy_spec.key, dramaturgy)
    return dramaturgy


def _agents(spec: Optional[AgentsSpec], refs: "_References") -> list[BaseAgent]:
    """作品のエージェントを職能の順(AGENT_ROLES、最後にActor)に組み立てる。Actorの配役はIDで参照する。
    省略したrole・rules・prohibitions・タスク(とタスクの中の項目)は、システム既定(core/default/agents/)で補う。"""
    if spec is None:
        return []
    agents: list[BaseAgent] = []
    for role_name in AGENT_ROLES:
        for agent_spec in getattr(spec, f"{role_name}s"):
            full = complete_agent_spec(role_name, agent_spec)
            agent = build_agent(
                role_name,
                full.name,
                full.role,
                full.persona,
                full.rules,
                full.prohibitions,
                _tasks(full),
                id=full.id,
            )
            refs.register("Agent", full.key, agent)
            agents.append(agent)
    for actor_spec in spec.actors:
        full = complete_agent_spec("actor", actor_spec)
        cast = refs.resolve("Cast", full.cast, f"演者 '{full.name}'")
        actor = build_actor(
            cast.id,
            full.name,
            full.voice_name,
            full.role,
            full.persona,
            full.rules,
            full.prohibitions,
            _tasks(full),
            id=full.id,
        )
        refs.register("Agent", full.key, actor)
        agents.append(actor)
    return agents


def _tasks(spec: AgentSpec) -> list[AgentTask]:
    return [AgentTask(t.code, t.title, t.description, t.rules, t.prohibitions) for t in spec.tasks]


def _situation(
    spec: Optional[SituationSpec], refs: "_References", where: str
) -> Optional[Situation]:
    if spec is None:
        return None
    return Situation(
        refs.resolve("Location", spec.location, f"{where}の状況"),
        spec.description,
        spec.time_of_day,
        spec.environment,
    )


def _speech_style(spec: Optional[SpeechStyleSpec]) -> Optional[SpeechStyle]:
    if spec is None:
        return None
    return SpeechStyle(
        spec.first_person,
        spec.tone,
        [SentenceEnding(e.kind, e.examples, e.description) for e in spec.endings],
        spec.description,
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


def _proposal(spec: Optional[ProposalSpec]) -> Optional[Proposal]:
    """企画書(省略されていればNone。作品は空の企画書を持つ)。"""
    if spec is None:
        return None
    return Proposal(
        spec.title,
        spec.catchphrase,
        spec.logline,
        spec.intent,
        spec.target_area,
        spec.synopsis,
        [ProposalCharacter(c.name, c.description) for c in spec.characters],
    )


def _order(order: Optional[int], index: int) -> int:
    """orderを省略したら、並びの中の位置(0から)。"""
    return order if order is not None else index
