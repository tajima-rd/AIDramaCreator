# tests/core/test_drama_draft_editor.py
"""
作品モデルのDB(正本・版・下書き。core.infra.store.drama_model_store・drama_version_store、
core.service.process.edit.drama_draft_editor)。tmp_pathの中のproject.dbだけを使う。
"""

import sqlite3
from pathlib import Path

import pytest

from core.infra.io.model_definition_reader import (
    build_model_definition_from_yaml,
    read_model_definition,
)
from core.infra.io.model_definition_writer import model_definition_to_yaml
from core.infra.store.drama_version_store import DraftNotFoundError
from core.model.agent import Scriptwriter
from core.model.drama import Dialogue, SoundEffect
from core.service.process.edit import drama_draft_editor as editor
from core.service.process.edit.drama_draft_editor import DraftConflictError

SAMPLE_DRAMA_DIR = (
    Path(__file__).resolve().parents[2] / "apps" / "sample_data" / "令和但馬道中膝栗毛" / "drama"
)

# 作品が2つ。人物・人物関係は両方の作品が参照する。どこからも参照しない時点・場所もある
PROJECT_MODEL = """
protocol_version: "0.1.0"
temporal_nodes:
  - key: childhood
    label: 少年時代
  - key: now
    label: 現在
    date_type: year
    string_date: "2026"
  - key: unused_node
    label: どこからも参照しない時点
locations:
  - key: lighthouse
    name: 灯台
    latitude: 34.6
    longitude: 135.0
  - key: harbor
    name: 港
  - key: unused_place
    name: どこからも参照しない場所
characters:
  - key: taro
    name: 太郎
    speech_style:
      first_person: 僕
      tone: 穏やか
      endings:
        - kind: normal
          examples: [〜だ。, 〜だよ。]
        - kind: question
          examples: [〜かい？]
          description: 優しく聞く
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
character_groups:
  - key: family
    name: 灯台守の家
    kind: 家族
    members: [{ref: father}, {ref: taro}]
relationships:
  - key: taro_father
    source: {ref: taro}
    target: {ref: father}
    label: 親子
    form_of_address: 父さん
    tone: 敬語
    period: {ref: childhood}
dramaturgies:
  - key: first
    title: 港町の灯
    input_language: ja
    output_language: zh
    premise:
      text: |
        観光の振興。
        港の歴史を伝える。
    proposal:
      title: 港の灯(仮)
      catchphrase: 灯台が見てきた百年
      logline: 灯台守の少年が、父の秘密を知る。
      intent: 港の歴史を、地元の子どもに伝える。
      target_area: 港町
      synopsis: 少年は灯台で古い日誌を見つける。
      characters:
        - name: 少年
          description: 灯台守の息子(仮)
        - name: 父
    characters: [{ref: taro}, {ref: father}]
    relationships: [{ref: taro_father}]
    casts:
      - key: taro_voice
        character: {ref: taro}
        voice_gender: male
        performance:
          title: Quiet Keeper
          pace: ゆっくり
    agents:
      scriptwriters:
        - key: writer
          name: 脚本家
          persona: 港町の生まれ
          rules: [潮の香りを言葉で描く。]
          tasks:
            - code: write_dialogue
              prohibitions: [標準語にしない。]
      actors:
        - key: taro_actor
          name: 太郎役の演者
          cast: {ref: taro_voice}
          voice_name: Charon
    acts:
      - key: act1
        title: 第一幕
        scenes:
          - key: night
            title: 灯台の夜
            period: {ref: now}
            location: {ref: lighthouse}
            situation:
              location: {ref: lighthouse}
              description: 灯を点検している
              time_of_day: 夜
            script:
              lines:
                - key: l1
                  cast: {ref: taro_voice}
                  text: 今夜も灯をともす。
                - key: l2
                  cast: {ref: taro_voice}
                  text: 港へ下りよう。
            elements:
              - type: sound_effect
              - type: dialogue
                line: {ref: l1}
                cast: {ref: taro_voice}
                text: "[静かに] 今夜も灯をともす。"
                direction:
                  pace: ゆっくり
                  pause_after: 長め
              - type: dialogue
                line: {ref: l2}
                cast: {ref: taro_voice}
                text: 港へ下りよう。
                translated_text: 去港口吧。
                situation:
                  location: {ref: harbor}
                  environment: 霧
              - type: dialogue
                line: {ref: l2}
                cast: {ref: taro_voice}
                text: 港へ下りよう。
                situation: {}
    history:
      edges:
        - kind: before
          source: {ref: childhood}
          target: {ref: now}
  - key: second
    title: 港町の灯(続編)
    characters: [{ref: father}]
    relationships: [{ref: taro_father}]
    casts:
      - key: father_voice
        character: {ref: father}
"""


@pytest.fixture
def db_path(tmp_path) -> str:
    return str(tmp_path / "TEST_PROJECT_00" / "project.db")


def _confirmed(db_path: str, yaml_text: str, note: str = "取り込み", replace: bool = False) -> int:
    draft = editor.create_draft(db_path, "取り込み")
    editor.import_yaml(db_path, draft.id, yaml_text, replace=replace)
    return editor.confirm_draft(db_path, draft.id, note)


def _normalized(yaml_text: str) -> str:
    return model_definition_to_yaml(build_model_definition_from_yaml(yaml_text))


def _without_ids(yaml_text: str) -> str:
    return "\n".join(
        line for line in yaml_text.splitlines() if not line.lstrip("- ").startswith("id: ")
    )


def test_project_model_with_two_dramaturgies_round_trips_through_yaml():
    definition = build_model_definition_from_yaml(PROJECT_MODEL)
    assert [d.title for d in definition.dramaturgies] == ["港町の灯", "港町の灯(続編)"]
    # 人物は作品をまたいで共有される
    assert definition.dramaturgies[1].characters[0] is definition.dramaturgies[0].characters[1]
    # どこからも参照しない時点・場所も、プロジェクトの作品モデルには残る
    assert [n.label for n in definition.temporal_nodes][-1] == "どこからも参照しない時点"
    assert [p.name for p in definition.locations][-1] == "どこからも参照しない場所"
    with pytest.raises(ValueError, match="作品が2個"):
        _ = definition.dramaturgy

    text = model_definition_to_yaml(definition)
    assert "dramaturgies:" in text and "\ndramaturgy:" not in text
    assert model_definition_to_yaml(build_model_definition_from_yaml(text)) == text


def test_confirmed_model_round_trips_through_db(db_path):
    version = _confirmed(db_path, PROJECT_MODEL)
    assert version == 1
    loaded = editor.load_model(db_path)
    snapshot = editor.version_yaml(db_path, version)
    # 正本から組み立て直したものは、版の写しと同じ(取り込んだときに付いたidも保つ)
    assert model_definition_to_yaml(loaded) == snapshot
    # 版の写しは、取り込んだ内容とidを除いて同じ
    assert _without_ids(snapshot) == _without_ids(_normalized(PROJECT_MODEL))

    scene = loaded.dramaturgies[0].acts[0].scenes[0]
    sound, quiet, harbor, empty = scene.elements
    assert isinstance(sound, SoundEffect)
    assert isinstance(quiet, Dialogue) and quiet.situation is None
    assert quiet.direction.pause_after == "長め"
    assert quiet.line_id == scene.script.lines[0].id
    assert harbor.situation.location.name == "港"
    assert harbor.translated_text == "去港口吧。"
    # 省略した状況(None)と、空の状況は区別される
    assert empty.situation is not None and empty.situation.description is None
    assert scene.situation.location is scene.location

    taro = loaded.characters[0]
    assert [e.examples for e in taro.speech_style.endings] == [["〜だ。", "〜だよ。"], ["〜かい？"]]
    assert [f.item for f in taro.characteristics[0].features] == ["職業", "灯台守"]
    # 人物関係は両端の人物から引ける(保存しないが、組み立てるとそろう)
    assert taro.relationships == loaded.characters[1].relationships == loaded.relationships
    assert taro.biographies[0].involved_relationships == loaded.relationships
    assert [m.name for m in loaded.character_groups[0].members] == ["父", "太郎"]

    # 企画書は作品の人物とは別に、仮の登場人物を持つ。企画書を書かなかった作品は空の企画書を持つ
    proposal = loaded.dramaturgies[0].proposal
    assert (proposal.title, proposal.target_area) == ("港の灯(仮)", "港町")
    assert [(c.name, c.description) for c in proposal.characters] == [
        ("少年", "灯台守の息子(仮)"),
        ("父", None),
    ]
    assert loaded.dramaturgies[1].proposal.title is None
    assert loaded.dramaturgies[1].proposal.characters == []

    # エージェントは作品が持つ。書き換えた文面と、既定のままの文面の両方が保たれる
    writer, actor = loaded.dramaturgies[0].agents
    assert (writer.name, writer.persona, writer.rules) == (
        "脚本家",
        "港町の生まれ",
        ["潮の香りを言葉で描く。"],
    )
    assert writer.prohibitions == Scriptwriter.default_prohibitions()
    dialogue = next(t for t in writer.tasks if t.code == "write_dialogue")
    assert dialogue.prohibitions == ["標準語にしない。"]
    assert [t.code for t in writer.tasks] == [t.code for t in Scriptwriter.default_tasks()]
    assert (actor.casting_id, actor.voice_name) == (loaded.dramaturgies[0].casts[0].id, "Charon")
    assert loaded.dramaturgies[1].agents == []


def test_sample_data_round_trips_through_db(db_path):
    draft = editor.create_draft(db_path, "サンプル")
    editor.import_definition(db_path, draft.id, SAMPLE_DRAMA_DIR)
    editor.confirm_draft(db_path, draft.id)
    expected = model_definition_to_yaml(read_model_definition(SAMPLE_DRAMA_DIR))
    assert model_definition_to_yaml(editor.load_model(db_path)) == expected


def test_draft_does_not_change_the_canonical_model_until_confirmed(db_path):
    draft = editor.create_draft(db_path)
    assert draft.base_version is None and draft.status == "open"
    editor.import_yaml(db_path, draft.id, PROJECT_MODEL)
    assert editor.load_model(db_path).dramaturgies == []
    assert editor.current_version(db_path) is None

    editor.confirm_draft(db_path, draft.id)
    assert editor.current_version(db_path) == 1
    assert editor.read_draft(db_path, draft.id).status == "confirmed"
    # 確定した下書きは、もう変えられない
    with pytest.raises(ValueError, match="confirmed"):
        editor.edit_draft(db_path, draft.id, PROJECT_MODEL)


def test_new_draft_starts_from_latest_version_and_keeps_ids(db_path):
    _confirmed(db_path, PROJECT_MODEL)
    draft = editor.create_draft(db_path, "続き")
    assert draft.base_version == 1
    assert editor.draft_yaml(db_path, draft.id) == editor.version_yaml(db_path, 1)

    model = editor.load_draft_model(db_path, draft.id)
    model.dramaturgies[0].title = "港町の灯(改)"
    editor.edit_draft(db_path, draft.id, model_definition_to_yaml(model))
    assert editor.confirm_draft(db_path, draft.id, "題を変えた") == 2

    loaded = editor.load_model(db_path)
    assert loaded.dramaturgies[0].title == "港町の灯(改)"
    assert loaded.dramaturgies[0].id == model.dramaturgies[0].id
    assert [(v.version, v.note) for v in editor.list_versions(db_path)] == [
        (1, "取り込み"),
        (2, "題を変えた"),
    ]


def test_undo_goes_back_one_change_at_a_time_without_erasing_history(db_path):
    draft = editor.create_draft(db_path)
    empty = editor.draft_yaml(db_path, draft.id)
    editor.import_yaml(db_path, draft.id, PROJECT_MODEL)
    imported = editor.draft_yaml(db_path, draft.id)
    model = editor.load_draft_model(db_path, draft.id)
    model.dramaturgies[1].title = "提案された題"
    editor.apply_to_draft(db_path, draft.id, model_definition_to_yaml(model))

    editor.undo(db_path, draft.id)
    assert editor.draft_yaml(db_path, draft.id) == imported
    # 続けてUndoすると、さらに前の変更まで遡る
    editor.undo(db_path, draft.id)
    assert editor.draft_yaml(db_path, draft.id) == empty
    with pytest.raises(ValueError, match="取り消せる変更がありません"):
        editor.undo(db_path, draft.id)

    assert [r.operation for r in editor.list_revisions(db_path, draft.id)] == [
        "create",
        "import",
        "apply",
        "undo",
        "undo",
    ]


def test_confirm_is_refused_when_another_draft_was_confirmed_first(db_path):
    _confirmed(db_path, PROJECT_MODEL)
    first = editor.create_draft(db_path, "1つ目")
    second = editor.create_draft(db_path, "2つ目")
    editor.confirm_draft(db_path, first.id)
    with pytest.raises(DraftConflictError, match="作り直して"):
        editor.confirm_draft(db_path, second.id)
    assert editor.current_version(db_path) == 2
    assert editor.read_draft(db_path, second.id).status == "open"


def test_failed_confirm_leaves_canonical_model_and_versions_unchanged(db_path, monkeypatch):
    _confirmed(db_path, PROJECT_MODEL)
    draft = editor.create_draft(db_path)
    editor.import_yaml(db_path, draft.id, "dramaturgy: {title: 別の作品}")

    def fail(*args, **kwargs):
        raise RuntimeError("版の記録に失敗")

    monkeypatch.setattr(editor.drama_version_store, "add_version", fail)
    with pytest.raises(RuntimeError):
        editor.confirm_draft(db_path, draft.id)
    # 正本の書き直しも取り消される(1つのトランザクション)
    assert [d.title for d in editor.load_model(db_path).dramaturgies] == [
        "港町の灯",
        "港町の灯(続編)",
    ]
    assert editor.current_version(db_path) == 1


def test_discarded_draft_cannot_be_confirmed(db_path):
    draft = editor.create_draft(db_path)
    editor.discard_draft(db_path, draft.id)
    assert editor.list_drafts(db_path, "open") == []
    with pytest.raises(ValueError, match="discarded"):
        editor.confirm_draft(db_path, draft.id)


def test_invalid_yaml_is_not_stored_in_draft(db_path):
    draft = editor.create_draft(db_path)
    with pytest.raises(ValueError, match="key 'nobody'"):
        editor.edit_draft(
            db_path,
            draft.id,
            "dramaturgy: {title: 題, casts: [{character: {ref: nobody}}]}",
        )
    # 職能に無いタスクを持つエージェント
    agents = "dramaturgy: {title: 題, agents: {scriptwriters: [{name: 脚本家, tasks: [{code: nope}]}]}}\n"
    with pytest.raises(ValueError, match="タスク 'nope'"):
        editor.import_yaml(db_path, draft.id, agents)
    assert len(editor.list_revisions(db_path, draft.id)) == 1


def test_unknown_draft_raises_not_found(db_path):
    with pytest.raises(DraftNotFoundError):
        editor.confirm_draft(db_path, "no-such-draft")


def test_confirm_rewrites_all_rows(db_path):
    _confirmed(db_path, PROJECT_MODEL)
    _confirmed(db_path, "dramaturgy: {title: 小さな作品}", replace=True)
    conn = sqlite3.connect(db_path)
    try:
        counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("character", "relationship", "scene", "script_element", "location")
        }
        titles = [row[0] for row in conn.execute("SELECT title FROM dramaturgy")]
    finally:
        conn.close()
    assert counts == dict.fromkeys(counts, 0)
    assert titles == ["小さな作品"]
