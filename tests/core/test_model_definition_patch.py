# tests/core/test_model_definition_patch.py
"""
部分YAMLの重ね合わせ(core.infra.io.model_definition_patch)と、下書きへの反映(drama_draft_editor)。
docs/database_design.md「部分YAMLの重ね合わせ」の規則ごと。tmp_pathの中のproject.dbだけを使う。
"""

import pytest
import yaml

from core.infra.io.model_definition_patch import patch_spec
from core.infra.io.agent_default_reader import system_default
from core.service.process.edit import drama_draft_editor as editor
from tests.core.test_drama_draft_editor import PROJECT_MODEL


@pytest.fixture
def db_path(tmp_path) -> str:
    return str(tmp_path / "TEST_PROJECT_00" / "project.db")


@pytest.fixture
def draft_id(db_path) -> str:
    draft = editor.create_draft(db_path)
    editor.import_yaml(db_path, draft.id, PROJECT_MODEL)
    return draft.id


def _content(db_path: str, draft_id: str) -> dict:
    return yaml.safe_load(editor.draft_yaml(db_path, draft_id))


def _character(content: dict, name: str) -> dict:
    return next(c for c in content["characters"] if c["name"] == name)


def test_item_is_found_by_id_or_key_and_overwritten(db_path, draft_id):
    before = _content(db_path, draft_id)
    taro = _character(before, "太郎")
    # idで特定して上書きし、書かなかった属性は残る
    editor.edit_draft(db_path, draft_id, f"characters: [{{id: {taro['id']}, reading: たろう}}]")
    # keyでも特定できる(最新の中身のkey)
    editor.edit_draft(db_path, draft_id, f"characters: [{{key: {taro['key']}, age: '12'}}]")
    after = _character(_content(db_path, draft_id), "太郎")
    assert (after["id"], after["reading"], after["age"]) == (taro["id"], "たろう", "12")
    assert after["speech_style"] == taro["speech_style"]
    assert len(_content(db_path, draft_id)["characters"]) == len(before["characters"])


def test_item_without_match_is_added(db_path, draft_id):
    editor.apply_to_draft(db_path, draft_id, "characters: [{name: 母}]")
    content = _content(db_path, draft_id)
    assert [c["name"] for c in content["characters"]] == ["太郎", "父", "母"]
    # 追加した要素にはidが付く
    assert _character(content, "母")["id"]


def test_null_removes_attribute(db_path, draft_id):
    first = _content(db_path, draft_id)["dramaturgies"][0]
    assert first["output_language"] == "zh"
    editor.edit_draft(
        db_path, draft_id, f"dramaturgies: [{{id: {first['id']}, output_language: null}}]"
    )
    assert "output_language" not in _content(db_path, draft_id)["dramaturgies"][0]


def test_lists_without_id_are_replaced_whole(db_path, draft_id):
    content = _content(db_path, draft_id)
    taro = _character(content, "太郎")
    first = content["dramaturgies"][0]
    father_key = _character(content, "父")["key"]
    patch = f"""
characters:
  - id: {taro['id']}
    characteristics:
      - item: 趣味
        features: [{{item: 釣り}}]
dramaturgies:
  - id: {first['id']}
    characters: [{{ref: {father_key}}}]
"""
    editor.edit_draft(db_path, draft_id, patch)
    after = _content(db_path, draft_id)
    assert [c["item"] for c in _character(after, "太郎")["characteristics"]] == ["趣味"]
    # 作品の人物は参照の一覧なので丸ごと置き換わる(最上位の人物はそのまま)
    assert after["dramaturgies"][0]["characters"] == [{"ref": _character(after, "父")["key"]}]
    assert len(after["characters"]) == 2


def test_proposal_is_overlaid_and_its_characters_are_replaced_whole(db_path, draft_id):
    first = _content(db_path, draft_id)["dramaturgies"][0]
    patch = f"""
dramaturgies:
  - id: {first['id']}
    proposal:
      logline: 灯台守の少女が、祖父の秘密を知る。
      characters: [{{name: 少女}}]
"""
    editor.edit_draft(db_path, draft_id, patch)
    proposal = _content(db_path, draft_id)["dramaturgies"][0]["proposal"]
    # 書かなかった項目は残り、登場人物(識別子の無い仮の設定)の一覧は丸ごと置き換わる
    assert proposal["title"] == first["proposal"]["title"]
    assert proposal["logline"] == "灯台守の少女が、祖父の秘密を知る。"
    assert proposal["characters"] == [{"name": "少女"}]
    # 企画書の登場人物は作品の人物(参照)とは別
    assert _content(db_path, draft_id)["dramaturgies"][0]["characters"] == first["characters"]


def test_proposal_can_be_added_to_dramaturgy_without_one(db_path, draft_id):
    second = _content(db_path, draft_id)["dramaturgies"][1]
    assert "proposal" not in second
    editor.edit_draft(
        db_path,
        draft_id,
        f"dramaturgies: [{{id: {second['id']}, proposal: {{target_area: 山村}}}}]",
    )
    assert _content(db_path, draft_id)["dramaturgies"][1]["proposal"] == {"target_area": "山村"}


def _writer(content: dict) -> dict:
    return content["dramaturgies"][0]["agents"]["scriptwriters"][0]


def test_agent_lists_are_replaced_whole_and_null_restores_defaults(db_path, draft_id):
    first = _content(db_path, draft_id)["dramaturgies"][0]
    writer = _writer(_content(db_path, draft_id))
    patch = f"""
dramaturgies:
  - id: {first['id']}
    agents:
      scriptwriters:
        - id: {writer['id']}
          prohibitions: [長い独白を書かない。]
          tasks: [{{code: draft_proposal, title: 企画を相談する}}]
"""
    editor.edit_draft(db_path, draft_id, patch)
    after = _writer(_content(db_path, draft_id))
    assert after["prohibitions"] == ["長い独白を書かない。"]
    # タスクの一覧は丸ごと置き換わり、書かなかったタスクは既定に戻る
    titles = {t["code"]: t["title"] for t in after["tasks"]}
    assert titles["draft_proposal"] == "企画を相談する"
    dialogue = next(t for t in after["tasks"] if t["code"] == "write_dialogue")
    default = system_default("scriptwriter")
    assert (
        dialogue["prohibitions"]
        == next(t for t in default.tasks if t.code == "write_dialogue").prohibitions
    )
    # 書かなかった属性は残る
    assert after["rules"] == writer["rules"] and after["persona"] == writer["persona"]

    # nullで消すと、職能の既定に戻る
    editor.edit_draft(
        db_path,
        draft_id,
        f"dramaturgies: [{{id: {first['id']}, agents: {{scriptwriters: "
        f"[{{id: {writer['id']}, rules: null, prohibitions: null, tasks: null}}]}}}}]",
    )
    reset = _writer(_content(db_path, draft_id))
    assert reset["rules"] == default.rules
    assert reset["prohibitions"] == default.prohibitions
    assert [t["title"] for t in reset["tasks"]] == [t.title for t in default.tasks]


def test_delete_removes_item_and_owned_children(db_path, draft_id):
    content = _content(db_path, draft_id)
    scene = content["dramaturgies"][0]["acts"][0]["scenes"][0]
    act = content["dramaturgies"][0]["acts"][0]
    patch = f"""
dramaturgies:
  - id: {content['dramaturgies'][0]['id']}
    acts:
      - id: {act['id']}
        scenes:
          - {{id: {scene['id']}, delete: true}}
"""
    editor.edit_draft(db_path, draft_id, patch)
    model = editor.load_draft_model(db_path, draft_id)
    # シーンと一緒に、台詞・原稿も消える
    assert model.dramaturgies[0].acts[0].scenes == []


def test_deleting_referenced_item_is_refused(db_path, draft_id):
    content = _content(db_path, draft_id)
    father = _character(content, "父")
    revisions = len(editor.list_revisions(db_path, draft_id))
    # 父は人物関係・作品・配役から参照されている
    with pytest.raises(ValueError, match="key"):
        editor.edit_draft(db_path, draft_id, f"characters: [{{id: {father['id']}, delete: true}}]")
    assert len(editor.list_revisions(db_path, draft_id)) == revisions


def test_delete_of_missing_item_is_refused(db_path, draft_id):
    with pytest.raises(ValueError, match="その要素がありません"):
        editor.edit_draft(db_path, draft_id, "locations: [{key: nowhere, delete: true}]")


def test_singular_dramaturgy_overlays_matching_item(db_path, draft_id):
    second = _content(db_path, draft_id)["dramaturgies"][1]
    editor.edit_draft(
        db_path, draft_id, f"dramaturgy: {{id: {second['id']}, synopsis: 続編のあらすじ}}"
    )
    dramaturgies = _content(db_path, draft_id)["dramaturgies"]
    assert len(dramaturgies) == 2
    assert dramaturgies[1]["synopsis"] == "続編のあらすじ"


def test_split_documents_are_merged_before_overlay(db_path):
    # 分割した文書は、属する作品のidを書かないことがある。1つにまとめてから重ねるので、別の作品にならない
    draft = editor.create_draft(db_path)
    editor.import_yaml(
        db_path,
        draft.id,
        "dramaturgy: {key: d, title: 題}",
        "dramaturgy: {acts: [{key: a, title: 第一幕}]}",
    )
    model = editor.load_draft_model(db_path, draft.id)
    assert [d.title for d in model.dramaturgies] == ["題"]
    assert [a.title for a in model.dramaturgy.acts] == ["第一幕"]


def test_replace_import_discards_current_content(db_path, draft_id):
    editor.import_yaml(db_path, draft_id, "dramaturgy: {title: 新しい作品}", replace=True)
    content = _content(db_path, draft_id)
    assert [d["title"] for d in content["dramaturgies"]] == ["新しい作品"]
    assert "characters" not in content


def test_patch_spec_does_not_change_base():
    base = {"characters": [{"id": "c1", "name": "太郎"}]}
    result = patch_spec(base, [{"characters": [{"id": "c1", "name": "次郎"}]}])
    assert base["characters"][0]["name"] == "太郎"
    assert result["characters"][0]["name"] == "次郎"


def test_delete_mark_inside_new_item_is_refused():
    with pytest.raises(ValueError, match="削除の印"):
        patch_spec(
            {}, [{"characters": [{"name": "太郎", "biographies": [{"key": "b", "delete": True}]}]}]
        )
