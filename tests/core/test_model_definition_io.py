# tests/core/test_model_definition_io.py
"""モデル定義YAML(core.infra.io.model_definition_reader・writer)の読み書き。tmp_pathの中だけで動く。"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from core.infra.io.model_definition_reader import (
    build_dramaturgy_from_yaml,
    read_dramaturgy,
)
from core.infra.io.model_definition_writer import (
    SPLIT_FILES,
    dramaturgy_to_spec,
    dramaturgy_to_split_yaml,
    dramaturgy_to_yaml,
    write_dramaturgy,
    write_split_dramaturgy,
)
from core.model.drama import Dialogue, Music, StringDateType, TemporalRelationKind

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
        source: childhood
        target: now
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
    source: taro
    target: father
    label: 親子
    period: childhood
dramaturgy:
  characters:
    - key: taro
      name: 太郎
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
        - period: childhood
          episode: 父と灯台に登った
          involved_relationship: taro_father
    - key: father
      name: 父
  casts:
    - key: taro_voice
      character: taro
      provider: gemini
      voice_name: Kore
"""

ACTS = """
dramaturgy:
  acts:
    - key: act1
      title: 第一幕
      scenes:
        - key: night
          title: 灯台の夜
          period: now
          location: lighthouse
          script:
            lines:
              - key: l1
                cast: taro_voice
                text: 今夜も灯をともす。
          elements:
            - type: music
            - type: dialogue
              line: l1
              cast: taro_voice
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
    source: taro
    target: father
    label: 親子
    period: childhood
dramaturgy:
  title: 港町の灯
  synopsis: 灯台守の家族の物語
  input_language: ja
  output_language: zh
  premise:
    text: |
      観光の振興。
      港の歴史を伝える。
  characters:
    - key: taro
      name: 太郎
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
        - period: childhood
          episode: 父と灯台に登った
          involved_relationship: taro_father
    - key: father
      name: 父
  casts:
    - key: taro_voice
      character: taro
      provider: gemini
      voice_name: Kore
  acts:
    - key: act1
      title: 第一幕
      scenes:
        - key: night
          title: 灯台の夜
          period: now
          location: lighthouse
          script:
            lines:
              - key: l1
                cast: taro_voice
                text: 今夜も灯をともす。
          elements:
            - type: music
            - type: dialogue
              line: l1
              cast: taro_voice
              text: "[静かに] 今夜も灯をともす。"
              direction:
                pace: ゆっくり
  history:
    edges:
      - kind: before
        source: childhood
        target: now
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
    assert biography.involved_relationship.source is taro
    assert biography.involved_relationship.target is father
    assert biography.involved_relationship.period is biography.period
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
    assert restored.characters[0].biographies[0].involved_relationship.id == (
        original.characters[0].biographies[0].involved_relationship.id
    )
    assert dramaturgy_to_spec(restored) == dramaturgy_to_spec(original)
    text = path.read_text(encoding="utf-8")
    assert "  premise:\n    text: |" in text  # 所有は入れ子。複数行はブロックの形
    assert "\n  characters:\n" in text and "\n    biographies:\n" in text


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
              line: l2
              cast: taro_voice
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
                cast: taro_voice
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
dramaturgy:
  characters:
    - name: 母
"""
    dramaturgy = build_dramaturgy_from_yaml(SINGLE, more)
    assert [c.name for c in dramaturgy.characters] == ["太郎", "父", "母"]


def test_split_output_is_readable_per_file():
    texts = dramaturgy_to_split_yaml(build_dramaturgy_from_yaml(SINGLE))
    assert texts["dramaturgy.yaml"].startswith("protocol_version:")
    assert (
        "title: 港町の灯" in texts["dramaturgy.yaml"]
        and "characters:" not in texts["dramaturgy.yaml"]
    )
    assert texts["casts.yaml"].startswith("dramaturgy:\n  casts:\n")  # 分けても入れ子の形


@pytest.mark.parametrize(
    "extra, message",
    [
        ("dramaturgy:\n  title: 別の題\n", "dramaturgy.title"),
        ("dramaturgy:\n  casts:\n    - character: nobody\n", "nobody"),
        ("dramaturgy:\n  characters:\n    - key: taro\n      name: 二人目の太郎\n", "taro"),
    ],
)
def test_invalid_definitions_raise(extra, message):
    with pytest.raises(ValueError, match=message):
        build_dramaturgy_from_yaml(SINGLE, extra)


def test_unknown_field_and_missing_title_raise():
    with pytest.raises(ValidationError):
        build_dramaturgy_from_yaml(SINGLE.replace("voice_name:", "voice:"))
    with pytest.raises(ValidationError):
        build_dramaturgy_from_yaml(CHARACTERS)


def test_split_refuses_directory_with_other_yaml(tmp_path):
    (tmp_path / "notes.yaml").write_text("a: 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="notes.yaml"):
        write_split_dramaturgy(build_dramaturgy_from_yaml(SINGLE), tmp_path)


def test_written_yaml_refers_by_id_without_keys():
    text = dramaturgy_to_yaml(build_dramaturgy_from_yaml(SINGLE))
    assert "key:" not in text


def test_sample_data_is_readable():
    # apps/sample_data(apps/sample_projectの人物・プロットを変換した、分割方式のモデル定義YAML)。読むだけ
    repo = Path(__file__).resolve().parents[2]
    dramaturgy = read_dramaturgy(repo / "apps" / "sample_data")

    plots = sorted((repo / "apps" / "sample_project" / "plot").glob("*.txt"))
    assert [s.synopsis for s in dramaturgy.acts[0].scenes] == [
        p.read_text(encoding="utf-8") for p in plots
    ]
    assert {"加藤 喜一", "水野 弥千代"} <= {c.name for c in dramaturgy.characters}


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


def test_relationships_are_reachable_from_both_characters():
    # 経歴から参照されない人物関係も、人物の側から引け、書き出しで失われない
    extra = """
relationships:
  - source: father
    target: taro
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
