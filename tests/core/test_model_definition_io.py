# tests/core/test_model_definition_io.py
"""モデル定義YAML(core.infra.io.model_definition_reader・writer)の読み書き。tmp_pathの中だけで動く。"""

import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from core.infra.io.model_definition_reader import (
    build_dramaturgy_from_yaml,
    build_model_definition_from_yaml,
    read_dramaturgy,
    read_model_definition,
)
from core.infra.io.model_definition_writer import (
    SPLIT_FILES,
    dramaturgy_to_spec,
    dramaturgy_to_split_yaml,
    dramaturgy_to_yaml,
    model_definition_to_yaml,
    write_dramaturgy,
    write_split_dramaturgy,
)
from core.infra.io.agent_default_reader import system_default
from core.model.agent import Actor, Scriptwriter
from core.model.drama import (
    Dialogue,
    Music,
    SentenceEndingKind,
    StringDateType,
    TemporalRelationKind,
    VoiceGender,
)

# 人が書く形(idを書かず、keyで参照する)。分割したときの各部分も、同じ入れ子の形の一部
HEADER = """
protocol_version: "0.1.0"
dramaturgy:
  title: 港町の灯
  synopsis: 灯台守の家族の物語
  input_language: ja
  output_language: zh
  premise:
    text: |
      観光の振興。
      港の歴史を伝える。
"""

TEMPORAL = """
temporal_nodes:
  - key: childhood
    label: 少年時代
  - key: now
    label: 現在
    date_type: year
    string_date: "2026"
dramaturgy:
  history:
    edges:
      - kind: before
        source: {ref: childhood}
        target: {ref: now}
"""

LOCATIONS = """
locations:
  - key: lighthouse
    name: 灯台
    latitude: 34.6
    longitude: 135.0
"""

CHARACTERS = """
relationships:
  - key: taro_father
    source: {ref: taro}
    target: {ref: father}
    label: 親子
    form_of_address: 父さん
    tone: 敬語
    period: {ref: childhood}
characters:
  - key: taro
    name: 太郎
    speech_style:
      first_person: 僕
      tone: 穏やか
      endings:
        - kind: normal
          examples: [〜だ。, 〜だよ。]
    characteristics:
      - item: 仕事
        features:
          - item: 職業
            value: 灯台守
          - item: 灯台守
            definition: 灯台の灯をともし、守る人
      - item: 性格
        description: 無口
    biographies:
      - period: {ref: childhood}
        episode: 父と灯台に登った
        involved_relationships: [{ref: taro_father}]
  - key: father
    name: 父
dramaturgy:
  characters: [{ref: taro}, {ref: father}]
  relationships: [{ref: taro_father}]
  casts:
    - key: taro_voice
      character: {ref: taro}
      performance:
        title: Quiet Keeper
        description: 口数は少ないが温かい
        pace: ゆっくり
"""

ACTS = """
dramaturgy:
  acts:
    - key: act1
      title: 第一幕
      scenes:
        - key: night
          title: 灯台の夜
          period: {ref: now}
          location: {ref: lighthouse}
          script:
            lines:
              - key: l1
                cast: {ref: taro_voice}
                text: 今夜も灯をともす。
          elements:
            - type: music
            - type: dialogue
              line: {ref: l1}
              cast: {ref: taro_voice}
              text: "[静かに] 今夜も灯をともす。"
              direction:
                pace: ゆっくり
"""

# 上の部分を1つの文書にまとめたもの
SINGLE = """
protocol_version: "0.1.0"
temporal_nodes:
  - key: childhood
    label: 少年時代
  - key: now
    label: 現在
    date_type: year
    string_date: "2026"
locations:
  - key: lighthouse
    name: 灯台
    latitude: 34.6
    longitude: 135.0
relationships:
  - key: taro_father
    source: {ref: taro}
    target: {ref: father}
    label: 親子
    form_of_address: 父さん
    tone: 敬語
    period: {ref: childhood}
characters:
  - key: taro
    name: 太郎
    speech_style:
      first_person: 僕
      tone: 穏やか
      endings:
        - kind: normal
          examples: [〜だ。, 〜だよ。]
    characteristics:
      - item: 仕事
        features:
          - item: 職業
            value: 灯台守
          - item: 灯台守
            definition: 灯台の灯をともし、守る人
      - item: 性格
        description: 無口
    biographies:
      - period: {ref: childhood}
        episode: 父と灯台に登った
        involved_relationships: [{ref: taro_father}]
  - key: father
    name: 父
dramaturgy:
  title: 港町の灯
  synopsis: 灯台守の家族の物語
  input_language: ja
  output_language: zh
  premise:
    text: |
      観光の振興。
      港の歴史を伝える。
  characters: [{ref: taro}, {ref: father}]
  relationships: [{ref: taro_father}]
  casts:
    - key: taro_voice
      character: {ref: taro}
      performance:
        title: Quiet Keeper
        description: 口数は少ないが温かい
        pace: ゆっくり
  acts:
    - key: act1
      title: 第一幕
      scenes:
        - key: night
          title: 灯台の夜
          period: {ref: now}
          location: {ref: lighthouse}
          script:
            lines:
              - key: l1
                cast: {ref: taro_voice}
                text: 今夜も灯をともす。
          elements:
            - type: music
            - type: dialogue
              line: {ref: l1}
              cast: {ref: taro_voice}
              text: "[静かに] 今夜も灯をともす。"
              direction:
                pace: ゆっくり
  history:
    edges:
      - kind: before
        source: {ref: childhood}
        target: {ref: now}
"""


def test_build_from_keys_resolves_references():
    dramaturgy = build_dramaturgy_from_yaml(SINGLE)

    assert dramaturgy.title == "港町の灯"
    assert dramaturgy.premise.text == "観光の振興。\n港の歴史を伝える。\n"
    taro, father = dramaturgy.characters
    work, personality = taro.characteristics
    assert [(f.item, f.value, f.definition) for f in work.features] == [
        ("職業", "灯台守", None),
        ("灯台守", None, "灯台の灯をともし、守る人"),
    ]
    assert (personality.item, personality.description, personality.features) == ("性格", "無口", [])
    biography = taro.biographies[0]
    assert biography.period.label == "少年時代"
    (involved,) = biography.involved_relationships
    assert involved.source is taro and involved.target is father
    assert involved.period is biography.period
    assert (involved.form_of_address, involved.tone) == ("父さん", "敬語")
    speech = taro.speech_style
    assert (speech.first_person, speech.tone) == ("僕", "穏やか")
    assert [(e.kind, e.examples) for e in speech.endings] == [
        (SentenceEndingKind.NORMAL, ["〜だ。", "〜だよ。"])
    ]
    assert dramaturgy.casts[0].performance.pace == "ゆっくり"
    edge = dramaturgy.history.edges[0]
    assert edge.kind is TemporalRelationKind.BEFORE
    assert edge.source is biography.period
    assert edge.target.date_type is StringDateType.YEAR
    cast = dramaturgy.casts[0]
    assert cast.character is taro

    scene = dramaturgy.acts[0].scenes[0]
    assert (dramaturgy.acts[0].order, scene.order) == (0, 0)  # orderの省略は並びの位置
    assert scene.period is edge.target
    assert scene.location.name == "灯台"
    line = scene.script.lines[0]
    assert line.cast is cast
    music, dialogue = scene.elements
    assert isinstance(music, Music) and music.order == 0
    assert isinstance(dialogue, Dialogue) and dialogue.order == 1
    assert (dialogue.line_id, dialogue.cast_id) == (line.id, cast.id)
    assert dialogue.direction.pace == "ゆっくり"


def test_single_file_round_trip_keeps_ids(tmp_path):
    original = build_dramaturgy_from_yaml(SINGLE)
    path = tmp_path / "model.yaml"
    write_dramaturgy(original, path)

    restored = read_dramaturgy(path)

    assert restored.id == original.id
    assert restored.characters[0].biographies[0].involved_relationships[0].id == (
        original.characters[0].biographies[0].involved_relationships[0].id
    )
    assert dramaturgy_to_spec(restored) == dramaturgy_to_spec(original)
    text = path.read_text(encoding="utf-8")
    assert "  premise:\n    text: |" in text  # 所有は入れ子。複数行はブロックの形
    assert "\ncharacters:\n" in text and "\n  biographies:\n" in text  # 人物は作品の外


def test_split_files_round_trip(tmp_path):
    original = build_dramaturgy_from_yaml(SINGLE, SCENE2, SCRIPT2)
    written = write_split_dramaturgy(original, tmp_path / "model")

    assert sorted(p.relative_to(tmp_path / "model").as_posix() for p in written) == sorted(
        [
            *SPLIT_FILES,
            "plots/act_000_scene_000.yaml",
            "plots/act_000_scene_001.yaml",
            "scripts/act_000_scene_000.yaml",
            "scripts/act_000_scene_001.yaml",
            "scenes/act_000_scene_000.yaml",
            "scenes/act_000_scene_001.yaml",
        ]
    )
    assert dramaturgy_to_spec(read_dramaturgy(tmp_path / "model")) == dramaturgy_to_spec(original)
    # 上書きもできる
    write_split_dramaturgy(original, tmp_path / "model")


# 幕act1に加えるシーンと、その台詞を、それぞれ別のファイルに書く(属する幕・シーンをkeyで示す)
SCENE2 = """
dramaturgy:
  acts:
    - key: act1
      scenes:
        - key: dawn
          order: 1
          title: 夜明け
          elements:
            - type: dialogue
              line: {ref: l2}
              cast: {ref: taro_voice}
              text: 朝だ。
"""

SCRIPT2 = """
dramaturgy:
  acts:
    - key: act1
      scenes:
        - key: dawn
          script:
            lines:
              - key: l2
                cast: {ref: taro_voice}
                text: 朝だ。
"""


def test_scene_and_script_in_separate_files(tmp_path):
    directory = tmp_path / "model"
    (directory / "scenes").mkdir(parents=True)
    (directory / "scripts").mkdir()
    (directory / "model.yaml").write_text(SINGLE, encoding="utf-8")
    (directory / "scenes" / "dawn.yaml").write_text(SCENE2, encoding="utf-8")
    (directory / "scripts" / "dawn.yaml").write_text(SCRIPT2, encoding="utf-8")

    act = read_dramaturgy(directory).acts[0]

    assert [scene.title for scene in act.scenes] == ["灯台の夜", "夜明け"]
    dawn = act.scenes[1]
    assert dawn.order == 1
    assert dawn.script.lines[0].text == "朝だ。"
    assert dawn.elements[0].line_id == dawn.script.lines[0].id


def test_split_removes_stale_scene_files(tmp_path):
    write_split_dramaturgy(build_dramaturgy_from_yaml(SINGLE, SCENE2, SCRIPT2), tmp_path)
    assert (tmp_path / "scenes" / "act_000_scene_001.yaml").exists()

    write_split_dramaturgy(build_dramaturgy_from_yaml(SINGLE), tmp_path)  # シーンが1つに減った

    for directory in ("plots", "scripts", "scenes"):
        assert not (tmp_path / directory / "act_000_scene_001.yaml").exists()
    assert len(read_dramaturgy(tmp_path).acts[0].scenes) == 1


def test_plot_only_file_can_be_imported():
    # プロット(シーンのあらすじ)だけのファイル。台詞・原稿はまだ無い
    plot = """
dramaturgy:
  acts:
    - key: act1
      scenes:
        - key: dawn
          order: 1
          synopsis: |
            夜が明ける。
"""
    dawn = build_dramaturgy_from_yaml(SINGLE, plot).acts[0].scenes[1]
    assert dawn.synopsis == "夜が明ける。\n"
    assert dawn.script.lines == [] and dawn.elements == []


def test_split_text_and_documents_equal_single():
    single = dramaturgy_to_spec(build_dramaturgy_from_yaml(SINGLE))

    # 区画を好きな順・好きな単位に分けてよい(1つの文字列の中の --- 区切りでもよい)
    by_texts = build_dramaturgy_from_yaml(ACTS, CHARACTERS, TEMPORAL + LOCATIONS, HEADER)
    by_documents = build_dramaturgy_from_yaml(
        "---\n".join([HEADER, TEMPORAL, LOCATIONS, CHARACTERS, ACTS])
    )

    for built in (by_texts, by_documents):
        spec = dramaturgy_to_spec(built)
        # idは読むたびに新しく振られるので、書き出したidをそろえてから比べる
        assert _without_ids(spec) == _without_ids(single)


def test_same_value_in_two_documents_is_allowed():
    dramaturgy = build_dramaturgy_from_yaml(SINGLE, "dramaturgy:\n  title: 港町の灯\n")
    assert dramaturgy.title == "港町の灯"


def test_list_sections_are_concatenated():
    more = """
characters:
  - key: mother
    name: 母
dramaturgy:
  characters: [{ref: mother}]
"""
    definition = build_model_definition_from_yaml(SINGLE, more)
    assert [c.name for c in definition.characters] == ["太郎", "父", "母"]
    assert [c.name for c in definition.dramaturgy.characters] == ["太郎", "父", "母"]


def test_characters_are_shared_not_owned():
    # 人物・人物関係は作品の外にあり(持ち主はProject。今はModelDefinition)、作品は関わるものを参照で持つ
    extra = """
characters:
  - key: stranger
    name: 作品に関わらない人物
"""
    definition = build_model_definition_from_yaml(SINGLE, extra)
    assert [c.name for c in definition.characters] == ["太郎", "父", "作品に関わらない人物"]
    assert [c.name for c in definition.dramaturgy.characters] == ["太郎", "父"]
    assert definition.dramaturgy.characters[0] is definition.characters[0]
    assert definition.dramaturgy.relationships == definition.relationships
    with pytest.raises(ValueError, match="nobody"):
        build_dramaturgy_from_yaml(SINGLE, "dramaturgy:\n  characters: [{ref: nobody}]\n")


def test_split_output_is_readable_per_file():
    texts = dramaturgy_to_split_yaml(build_dramaturgy_from_yaml(SINGLE))
    assert texts["dramaturgy.yaml"].startswith("protocol_version:")
    assert (
        "title: 港町の灯" in texts["dramaturgy.yaml"]
        and "name: 太郎" not in texts["dramaturgy.yaml"]  # 作品は人物を参照するだけ
    )
    assert texts["casts.yaml"].startswith("dramaturgy:\n  casts:\n")  # 分けても入れ子の形


@pytest.mark.parametrize(
    "extra, message",
    [
        ("dramaturgy:\n  title: 別の題\n", "dramaturgy.title"),
        ("dramaturgy:\n  casts:\n    - character: {ref: nobody}\n", "nobody"),
        ("characters:\n  - key: taro\n    name: 二人目の太郎\n", "taro"),
    ],
)
def test_invalid_definitions_raise(extra, message):
    with pytest.raises(ValueError, match=message):
        build_dramaturgy_from_yaml(SINGLE, extra)


def test_unknown_field_and_missing_title_raise():
    with pytest.raises(ValidationError):
        build_dramaturgy_from_yaml(SINGLE.replace("title: Quiet Keeper", "titel: Quiet Keeper"))
    with pytest.raises(ValidationError):
        build_dramaturgy_from_yaml(CHARACTERS)


def test_split_refuses_directory_with_other_yaml(tmp_path):
    (tmp_path / "notes.yaml").write_text("a: 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="notes.yaml"):
        write_split_dramaturgy(build_dramaturgy_from_yaml(SINGLE), tmp_path)


def test_written_yaml_has_id_and_key_and_refers_by_ref():
    dramaturgy = build_dramaturgy_from_yaml(SINGLE)
    spec = dramaturgy_to_spec(dramaturgy)
    taro = spec["characters"][0]
    cast = spec["dramaturgy"]["casts"][0]
    line = spec["dramaturgy"]["acts"][0]["scenes"][0]["script"]["lines"][0]

    # すべてのエンティティにidとkey(種類と通し番号)
    assert (taro["id"], taro["key"]) == (dramaturgy.characters[0].id, "character_001")
    assert taro["biographies"][0]["key"] == "biography_001"
    assert line["key"] == "scene_001_line_001"
    # 参照は {ref: key}(idでは書かない)
    assert cast["character"] == {"ref": "character_001"}
    assert line["cast"] == {"ref": "cast_001"}
    assert "character: {ref: character_001}" in dramaturgy_to_yaml(dramaturgy)


def test_reference_by_id_is_not_accepted():
    taro_id = build_dramaturgy_from_yaml(SINGLE).characters[0].id
    with_ids = SINGLE.replace("  - key: taro\n", f"  - id: {taro_id}\n    key: taro\n", 1)
    assert build_dramaturgy_from_yaml(with_ids).characters[0].id == taro_id  # idは保たれる
    with pytest.raises(ValueError, match="key"):
        build_dramaturgy_from_yaml(
            with_ids.replace("character: {ref: taro}", f"character: {{ref: {taro_id}}}", 1)
        )


def test_sample_data_is_readable(tmp_path):
    # apps/sample_data/令和但馬道中膝栗毛(分割方式のモデル定義YAML)。モデル定義はdrama/とagent/で、
    # apps/sample_data直下のproject.yamlはプロジェクトの見本(モデル定義ではない)。main.pyと同じく、2つをmodel/に複製して読む
    repo = Path(__file__).resolve().parents[2]
    for part in ("drama", "agent"):
        shutil.copytree(
            repo / "apps" / "sample_data" / "令和但馬道中膝栗毛" / part, tmp_path / "model" / part
        )
    definition = read_model_definition(tmp_path / "model")
    dramaturgy = definition.dramaturgy

    scenes = dramaturgy.acts[0].scenes
    assert len(scenes) == 5 and all(scene.synopsis for scene in scenes)
    assert {"加藤 喜一", "水野 弥千代"} <= {c.name for c in dramaturgy.characters}
    assert [(c.character.name, c.voice_gender) for c in dramaturgy.casts] == [
        ("加藤 喜一", VoiceGender.MALE),
        ("水野 弥千代", VoiceGender.FEMALE),
    ]
    assert [a.voice_name for a in dramaturgy.agents] == ["Charon", "Kore"]


def _without_ids(value):
    """比べるために、識別子とそれへの参照を位置の名前に置き換える。"""
    ids: dict[str, str] = {}

    def collect(node):
        if isinstance(node, dict):
            if "id" in node:
                ids.setdefault(node["id"], f"#{len(ids)}")
            for child in node.values():
                collect(child)
        elif isinstance(node, list):
            for child in node:
                collect(child)

    def replace(node):
        if isinstance(node, dict):
            return {key: replace(child) for key, child in node.items()}
        if isinstance(node, list):
            return [replace(child) for child in node]
        return ids.get(node, node) if isinstance(node, str) else node

    collect(value)
    return replace(value)


def test_hachikita_sample_has_proposal():
    # apps/sample_data/ハチ北スキー場ガイド: 企画書だけを持つ作品(幕・人物はまだ無い)
    repo = Path(__file__).resolve().parents[2]
    drama_dir = repo / "apps" / "sample_data" / "ハチ北スキー場ガイド" / "drama"
    definition = read_model_definition(drama_dir)
    proposal = definition.dramaturgy.proposal
    assert proposal.target_area == "ハチ北スキー場"
    assert proposal.title != definition.dramaturgy.title
    assert [c.name for c in proposal.characters] == ["西谷"]
    assert definition.dramaturgy.characters == [] and definition.dramaturgy.acts == []
    # 書き出して読み直しても同じ
    text = model_definition_to_yaml(definition)
    assert model_definition_to_yaml(build_model_definition_from_yaml(text)) == text


def test_relationships_are_reachable_from_both_characters():
    # 経歴から参照されない人物関係も、人物の側から引け、書き出しで失われない
    extra = """
relationships:
  - source: {ref: father}
    target: {ref: taro}
    label: 息子
dramaturgy:
  title: 港町の灯
"""
    dramaturgy = build_dramaturgy_from_yaml(SINGLE, extra)
    taro, father = dramaturgy.characters

    assert [r.label for r in taro.relationships] == ["親子", "息子"]
    assert [r.label for r in father.relationships] == ["親子", "息子"]
    restored = build_dramaturgy_from_yaml(dramaturgy_to_yaml(dramaturgy))
    assert [r.label for r in restored.characters[1].relationships] == ["親子", "息子"]


AGENTS = """
dramaturgy:
  agents:
    scriptwriters:
      - key: writer
        name: 脚本家
        persona: 簡潔な文体
        prohibitions: []
        tasks:
          - code: write_dialogue
            rules: [方言で書く。]
    actors:
      - key: taro_actor
        name: 太郎役の演者
        cast: {ref: taro_voice}
        voice_name: Charon
"""


def test_agents_are_read_with_dramaturgy_and_round_trip(tmp_path):
    definition = build_model_definition_from_yaml(SINGLE, AGENTS)
    writer, actor = definition.dramaturgy.agents

    assert isinstance(writer, Scriptwriter) and writer.persona == "簡潔な文体"
    assert isinstance(actor, Actor)
    cast = definition.dramaturgy.casts[0]
    assert (actor.casting_id, actor.voice_name) == (cast.id, "Charon")
    assert cast.performance.title == "Quiet Keeper"

    # 省略した項目は職能の既定、空の一覧[]は空のまま。タスクは書いたものだけを重ね、ほかは既定
    default = system_default("scriptwriter")
    assert writer.role == default.role
    assert writer.rules == default.rules
    assert writer.prohibitions == []
    assert [t.code for t in writer.tasks] == [t.code for t in default.tasks]
    dialogue = next(t for t in writer.tasks if t.code == "write_dialogue")
    assert dialogue.rules == ["方言で書く。"]
    assert (
        dialogue.description
        == next(t for t in default.tasks if t.code == "write_dialogue").description
    )
    assert actor.tasks[0].code == "perform_dialogue"

    write_split_dramaturgy(definition.dramaturgy, tmp_path / "model")
    assert (tmp_path / "model" / "agents.yaml").exists()
    restored = read_model_definition(tmp_path / "model")
    agents = restored.dramaturgy.agents
    assert [type(a).__name__ for a in agents] == ["Scriptwriter", "Actor"]
    assert agents[1].casting_id == restored.dramaturgy.casts[0].id == cast.id
    # 書き出しは全文を残すので、空の一覧も書き換えたタスクも保たれる
    assert agents[0].prohibitions == []
    assert next(t for t in agents[0].tasks if t.code == "write_dialogue").rules == ["方言で書く。"]
    with pytest.raises(ValueError, match="タスク 'no_such_task'"):
        build_model_definition_from_yaml(
            SINGLE, AGENTS.replace("code: write_dialogue", "code: no_such_task")
        )
    with pytest.raises(ValueError, match="nobody"):
        build_model_definition_from_yaml(
            SINGLE, AGENTS.replace("cast: {ref: taro_voice}", "cast: {ref: nobody}")
        )


def test_voice_gender_must_be_one_of_the_values():
    def with_voice_gender(value: str) -> str:
        return SINGLE.replace(
            "      performance:\n", f"      voice_gender: {value}\n      performance:\n", 1
        )

    with pytest.raises(ValidationError):
        build_dramaturgy_from_yaml(with_voice_gender("both"))
    cast = build_dramaturgy_from_yaml(with_voice_gender("neutral")).casts[0]
    assert cast.voice_gender is VoiceGender.NEUTRAL


def test_character_groups_reference_characters():
    groups = """
character_groups:
  - key: family
    name: 灯台守の家
    kind: 家族
    members: [{ref: taro}, {ref: father}]
"""
    definition = build_model_definition_from_yaml(SINGLE, groups)
    (group,) = definition.character_groups
    assert (group.name, group.kind) == ("灯台守の家", "家族")
    assert group.members == definition.characters  # 人物を参照で持つ(同じオブジェクト)

    spec = dramaturgy_to_spec(definition.dramaturgy, character_groups=definition.character_groups)
    assert spec["character_groups"][0]["members"] == [
        {"ref": "character_001"},
        {"ref": "character_002"},
    ]
    with pytest.raises(ValueError, match="nobody"):
        build_model_definition_from_yaml(SINGLE, groups.replace("{ref: father}", "{ref: nobody}"))


def test_scene_situation_and_dialogue_override():
    situation = """
dramaturgy:
  acts:
    - key: act1
      scenes:
        - key: night
          situation:
            description: 灯台の灯を点検している
            time_of_day: 夜
            environment: 雪
"""
    # 台詞は、場面の途中で変わるときだけ自分の状況を持つ(場所も上書きできる)
    override = SINGLE.replace(
        "              direction:\n                pace: ゆっくり\n",
        "              direction:\n                pace: ゆっくり\n"
        "              situation:\n"
        "                location: {ref: lighthouse}\n"
        "                description: 灯室に上がった\n",
        1,
    )
    dramaturgy = build_dramaturgy_from_yaml(override, situation)
    scene = dramaturgy.acts[0].scenes[0]
    assert (
        scene.situation.description,
        scene.situation.time_of_day,
        scene.situation.environment,
    ) == (
        "灯台の灯を点検している",
        "夜",
        "雪",
    )
    music, dialogue = scene.elements
    assert dialogue.situation.location is scene.location
    assert dialogue.situation.description == "灯室に上がった"

    restored = build_dramaturgy_from_yaml(dramaturgy_to_yaml(dramaturgy))
    restored_scene = restored.acts[0].scenes[0]
    assert restored_scene.situation.environment == "雪"
    assert restored_scene.elements[1].situation.location.name == "灯台"
