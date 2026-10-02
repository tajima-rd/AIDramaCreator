# tests/api/test_ai_build_world.py
"""
Build with AIの人物の工程(Characters・Groups・Relationships)の結合テスト。生成AIは偽物に差し替える。

- 追加と更新だけで削除はしない。既存の要素は名前で対応付け、空の値では既存の値を消さない
- Charactersの工程で出てきた人物は作品の登場人物に加え、新しい人物関係は作品の参照に加える
- いない人物を指すメンバー・関係は外して注意を返す。Groupsの工程は既存のまとまりのメンバーを置き換える
- 対話で提案が無ければ何も変えない
"""

import pytest

from core.prompt.ai_build.characters import (
    CharacterDraft,
    CharactersReply,
    GroupDraft,
    GroupsReply,
    RelationshipDraft,
    RelationshipsReply,
)
from tests.api.test_ai_build import (
    _action,
    _FakeGenerator,
    _send,
    fake,
)  # noqa: F401  (fakeはfixture)
from tests.conftest import parse_yaml

WORLD = """
characters:
  - key: nishitani
    name: 西谷
    gender: 男性
    characteristics: [{item: 人物像, features: [{item: 職業, value: コンセルジュ}]}]
  - {key: guest, name: 宿の客}
character_groups:
  - {key: staff, name: スキー場の人々, members: [{ref: nishitani}]}
relationships:
  - {key: r1, source: {ref: nishitani}, target: {ref: guest}, label: 案内する相手}
dramaturgy:
  title: ハチ北
  proposal:
    characters: [{name: 西谷, description: コンセルジュ}, {name: 父, description: 家族の長}]
  characters: [{ref: nishitani}]
  relationships: [{ref: r1}]
"""


@pytest.fixture
def world(client, project):
    pid = project.project_id
    created = parse_yaml(
        client.post(f"/projects/{pid}/drama-drafts", content="title: Dramaturgy Editor\n")
    )
    base = f"/projects/{pid}/drama-drafts/{created['draft_id']}"
    assert client.post(f"{base}/import", content=WORLD).status_code == 200
    content = parse_yaml(client.get(f"{base}/content"))
    return {
        "pid": pid,
        "draft_id": created["draft_id"],
        "base": base,
        "dramaturgy_id": content["dramaturgies"][0]["id"],
        "ai": f"/projects/{pid}/ai-build",
    }


def _reply(cls, has_proposal=True, **lists):
    return cls(
        message="作りました",
        has_proposal=has_proposal,
        evidence=[],
        questions=[],
        warnings=[],
        **lists,
    )


def _character(name, **values):
    base = dict(
        reading="",
        gender="",
        age="",
        first_person="",
        tone="",
        speech_description="",
        characteristics=[],
    )
    return CharacterDraft(name=name, **{**base, **values})


def _relationship(source, target, label, **values):
    base = dict(description="", form_of_address="", tone="")
    return RelationshipDraft(source=source, target=target, label=label, **{**base, **values})


def _by_name(items, name):
    return next(i for i in items if i["name"] == name)


def _content(client, world):
    return parse_yaml(client.get(f"{world['base']}/content"))


def test_characters_step_adds_and_updates_without_deleting(client, world, fake):  # noqa: F811
    fake["generator"] = _FakeGenerator(
        _reply(
            CharactersReply,
            characters=[
                _character("西谷", age="60代"),
                _character("父", gender="男性", first_person="俺"),
            ],
            groups=[GroupDraft(name="佐藤家", kind="家族", description="", members=["父", "母"])],
            relationships=[_relationship("父", "西谷", "案内人", form_of_address="西谷さん")],
        )
    )
    resp = _send(client, world, "one_shot", "人物を作って", step="characters")
    assert resp.status_code == 200, resp.text
    reply = parse_yaml(resp)
    assert fake["tasks"] == ["create_character"]
    assert reply["changed_fields"] == [
        "人物「西谷」を更新",
        "人物「父」を追加",
        "まとまり「佐藤家」を追加",
        "人物関係 父→西谷「案内人」を追加",
    ]
    assert any("母" in w for w in reply["warnings"])  # いない人物はメンバーから外す
    call = fake["generator"].calls[0]
    assert (
        "西谷" in call["messages"][-1].text and "家族の長" in call["messages"][-1].text
    )  # 人物と企画書を渡す
    assert "削除しない" in call["system"]

    _action(client, world, reply["id"], "apply")
    content = _content(client, world)
    nishitani = _by_name(content["characters"], "西谷")
    assert (nishitani["age"], nishitani["gender"]) == ("60代", "男性")  # 空で返した性別は消さない
    assert (
        nishitani["characteristics"][0]["features"][0]["value"] == "コンセルジュ"
    )  # 特徴を返さなければ残す
    father = _by_name(content["characters"], "父")
    assert father["speech_style"] == {"first_person": "俺"}
    assert {c["name"] for c in content["characters"]} == {"西谷", "宿の客", "父"}  # 削除しない
    keys = {c["key"]: c["name"] for c in content["characters"]}
    assert [keys[m["ref"]] for m in _by_name(content["character_groups"], "佐藤家")["members"]] == [
        "父"
    ]
    dramaturgy = content["dramaturgies"][0]
    assert sorted(keys[r["ref"]] for r in dramaturgy["characters"]) == [
        "父",
        "西谷",
    ]  # 作品の登場人物に加わる
    assert len(dramaturgy["relationships"]) == 2  # 新しい人物関係も作品の参照に加わる


def test_characters_step_keeps_existing_group_members(client, world, fake):  # noqa: F811
    fake["generator"] = _FakeGenerator(
        _reply(
            CharactersReply,
            characters=[],
            relationships=[],
            groups=[GroupDraft(name="スキー場の人々", kind="", description="", members=["宿の客"])],
        )
    )
    reply = parse_yaml(_send(client, world, "dialogue", "宿の客も加えて", step="characters"))
    _action(client, world, reply["id"], "apply")
    content = _content(client, world)
    keys = {c["key"]: c["name"] for c in content["characters"]}
    assert [keys[m["ref"]] for m in content["character_groups"][0]["members"]] == ["西谷", "宿の客"]


def test_groups_step_replaces_members_of_existing_group(client, world, fake):  # noqa: F811
    fake["generator"] = _FakeGenerator(
        _reply(
            GroupsReply,
            groups=[
                GroupDraft(name="スキー場の人々", kind="職場", description="", members=["宿の客"])
            ],
        )
    )
    reply = parse_yaml(_send(client, world, "dialogue", "メンバーを直して", step="groups"))
    assert fake["tasks"] == ["create_character_group"]
    assert reply["changed_fields"] == ["まとまり「スキー場の人々」を更新"]
    _action(client, world, reply["id"], "apply")
    content = _content(client, world)
    group = content["character_groups"][0]
    keys = {c["key"]: c["name"] for c in content["characters"]}
    assert group["kind"] == "職場" and [keys[m["ref"]] for m in group["members"]] == ["宿の客"]


def test_relationships_step_updates_matching_relationship(client, world, fake):  # noqa: F811
    fake["generator"] = _FakeGenerator(
        _reply(
            RelationshipsReply,
            relationships=[
                _relationship(
                    "西谷", "宿の客", "案内する相手", form_of_address="お客様", tone="丁寧"
                ),
                _relationship("西谷", "誰か", "知人"),
            ],
        )
    )
    reply = parse_yaml(_send(client, world, "one_shot", "", step="relationships"))
    assert fake["tasks"] == ["create_relationship"]
    assert reply["changed_fields"] == ["人物関係 西谷→宿の客「案内する相手」を更新"]
    assert any("誰か" in w for w in reply["warnings"])
    _action(client, world, reply["id"], "apply")
    relationship = _content(client, world)["relationships"][0]
    assert (relationship["form_of_address"], relationship["tone"]) == ("お客様", "丁寧")


def test_world_dialogue_without_proposal_changes_nothing(client, world, fake):  # noqa: F811
    fake["generator"] = _FakeGenerator(
        _reply(
            CharactersReply,
            has_proposal=False,
            characters=[_character("父")],
            groups=[],
            relationships=[],
        )
    )
    reply = parse_yaml(_send(client, world, "dialogue", "提案だけ聞かせて", step="characters"))
    assert reply["proposal"] is None and reply["proposal_status"] is None
