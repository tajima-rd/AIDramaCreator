# tests/api/test_character_import.py
"""
企画書の登場人物の取り込み(routers/character_import.py)の結合テスト。生成AIは偽物に差し替える。

- 未登録の登場人物は、骨組みから新しい人物になり、作品の人物の参照に加わること(下書きへのApply)
- 登録済みの人物(名前が同じ)は、作成を断り、矛盾の確認は下書きを変えずに理由を返すこと
- 統合は識別子を保ち、空の値で登録済みの値を消さないこと。置き換えは空の値を消し、語尾も空にすること
- 作品のScriptwriterの役割・タスクの文面を指示に含めること
- どちらのタスクも作業補助(assistive)の生成AIを使い、未設定なら400(作品作り用で代わりに動かさない)
- 名前の無い・企画書にいない登場人物は400、生成AIの呼び出しの失敗は502
"""

import pytest

from core.prompt.character_import import (
    CharacteristicSketch,
    CharacterConflictResponse,
    CharacterSketch,
    FeatureSketch,
)
from core.service.process.genai import character_importer
from tests.conftest import parse_yaml

MODEL = """
characters:
  - key: kiichi
    name: 加藤喜一
    reading: かとうきいち
    gender: 男性
    age: 40代
    speech_style:
      first_person: オレ
      endings: [{kind: normal, examples: [だよ]}]
    characteristics: [{item: 人物像, features: [{item: 職業, value: 会社員}]}]
dramaturgy:
  title: 続編
  proposal:
    title: 続編の企画
    synopsis: 喜一が旅館を継ぐ。
    characters:
      - {name: 加藤喜一, description: 50代の旅館の主人}
      - {name: " 女将 ", description: 旅館を切り盛りする}
      - {description: 名前の無い人物}
  characters: [{ref: kiichi}]
  agents:
    scriptwriters: [{name: 脚本家}]
"""


def _sketch(**values) -> CharacterSketch:
    base = dict(
        reading="",
        gender="",
        age="",
        first_person="",
        tone="",
        speech_description="",
        characteristics=[
            CharacteristicSketch(
                item="人物像",
                definition="",
                description="",
                features=[FeatureSketch(item="職業", value="旅館の主人", definition="", description="")],
            )
        ],
    )
    return CharacterSketch(**{**base, **values})


class _FakeGenerator:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def generate_structured(self, request, schema, system_instruction=None):
        self.calls.append((request, schema, str(system_instruction)))
        return self.response


@pytest.fixture
def fake(monkeypatch):
    """build_task_text_generatorを差し替え、使ったタスクを記録する。responseは各テストで入れる。"""
    state = {"tasks": [], "generator": None}

    def build(project, task_code, config=None):
        state["tasks"].append(task_code)
        return state["generator"]

    monkeypatch.setattr(character_importer, "build_task_text_generator", build)
    return state


@pytest.fixture
def draft(client, project):
    created = parse_yaml(client.post(f"/projects/{project.project_id}/drama-drafts", content="title: Dramaturgy Editor\n"))
    base = f"/projects/{project.project_id}/drama-drafts/{created['draft_id']}"
    assert client.post(f"{base}/import", content=MODEL).status_code == 200
    content = parse_yaml(client.get(f"{base}/content"))
    return {"base": base, "dramaturgy_id": content["dramaturgies"][0]["id"]}


def _content(client, draft):
    return parse_yaml(client.get(f"{draft['base']}/content"))


def _character(content, name):
    return next(c for c in content["characters"] if c["name"] == name)


def _import(client, draft, name, mode):
    body = {"dramaturgy_id": draft["dramaturgy_id"], "name": name, "mode": mode}
    return client.post(f"{draft['base']}/character-import", json=body)


def test_create_new_character(client, draft, fake):
    fake["generator"] = _FakeGenerator(_sketch(reading="おかみ", gender="女性", first_person="あたし"))
    resp = _import(client, draft, "女将", "create")
    assert resp.status_code == 200, resp.text
    result = parse_yaml(resp)
    assert fake["tasks"] == ["import_proposal_character"]

    content = _content(client, draft)
    created = _character(content, "女将")  # 企画書の名前の前後の空白は除く
    assert created["id"] == result["character_id"]
    assert (created["reading"], created["gender"]) == ("おかみ", "女性")
    assert "age" not in created  # 空の値は書かない
    assert created["speech_style"] == {"first_person": "あたし"}
    assert created["characteristics"] == [{"item": "人物像", "features": [{"item": "職業", "value": "旅館の主人"}]}]
    # 作品の人物の参照に加わる(既存の参照も残る)
    keys = {c["id"]: c["key"] for c in content["characters"]}
    refs = [r["ref"] for r in content["dramaturgies"][0]["characters"]]
    assert sorted(refs) == sorted([keys[created["id"]], keys[_character(content, "加藤喜一")["id"]]])

    revisions = parse_yaml(client.get(f"{draft['base']}/revisions"))["revisions"]
    assert revisions[-1]["operation"] == "apply"  # 生成AIの提案として反映する

    # 企画書の内容とScriptwriterの指示を渡す
    request, schema, instruction = fake["generator"].calls[0]
    assert "旅館を切り盛りする" in request and "喜一が旅館を継ぐ" in request
    assert schema is CharacterSketch
    assert "あなたは脚本家です" in instruction and "企画書の登場人物を取り込む" in instruction


def test_registered_character_requires_merge_or_replace(client, draft, fake):
    fake["generator"] = _FakeGenerator(_sketch())
    resp = _import(client, draft, "加藤喜一", "create")
    assert resp.status_code == 400 and "登録済み" in resp.json()["detail"]
    resp = _import(client, draft, "女将", "merge")
    assert resp.status_code == 400 and "登録されていません" in resp.json()["detail"]


def test_check_conflict_does_not_change_draft(client, draft, fake):
    fake["generator"] = _FakeGenerator(CharacterConflictResponse(conflict=True, reasons=[" 年齢: 登録は40代、企画書は50代 ", ""]))
    before = parse_yaml(client.get(f"{draft['base']}/revisions"))["revisions"]
    body = {"dramaturgy_id": draft["dramaturgy_id"], "name": "加藤喜一"}
    resp = client.post(f"{draft['base']}/character-import/check", json=body)
    assert resp.status_code == 200, resp.text
    result = parse_yaml(resp)
    assert result["conflict"] is True
    assert result["reasons"] == ["年齢: 登録は40代、企画書は50代"]
    assert result["character_id"] == _character(_content(client, draft), "加藤喜一")["id"]
    assert fake["tasks"] == ["check_character_conflict"]
    assert parse_yaml(client.get(f"{draft['base']}/revisions"))["revisions"] == before
    # 登録済みの設定を渡す
    assert "会社員" in fake["generator"].calls[0][0]

    body["name"] = "女将"
    assert client.post(f"{draft['base']}/character-import/check", json=body).status_code == 400  # 未登録


def test_merge_keeps_identity_and_existing_values(client, draft, fake):
    kiichi = _character(_content(client, draft), "加藤喜一")
    fake["generator"] = _FakeGenerator(_sketch(age="50代", tone="穏やか"))
    resp = _import(client, draft, "加藤喜一", "merge")
    assert resp.status_code == 200, resp.text
    assert parse_yaml(resp)["character_id"] == kiichi["id"]

    content = _content(client, draft)
    merged = _character(content, "加藤喜一")
    assert merged["id"] == kiichi["id"]
    assert (merged["age"], merged["gender"], merged["reading"]) == ("50代", "男性", "かとうきいち")  # 空の値は消さない
    assert merged["speech_style"]["first_person"] == "オレ" and merged["speech_style"]["tone"] == "穏やか"
    assert merged["speech_style"]["endings"] == kiichi["speech_style"]["endings"]  # 語尾は残す
    assert merged["characteristics"][0]["features"] == [{"item": "職業", "value": "旅館の主人"}]
    assert len(content["characters"]) == 1
    assert len(content["dramaturgies"][0]["characters"]) == 1  # 参照済みなので増えない


def test_replace_clears_values(client, draft, fake):
    fake["generator"] = _FakeGenerator(_sketch(age="50代"))
    resp = _import(client, draft, "加藤喜一", "replace")
    assert resp.status_code == 200, resp.text
    replaced = _character(_content(client, draft), "加藤喜一")
    assert replaced["age"] == "50代"
    assert "gender" not in replaced and "reading" not in replaced  # 空の値は消す
    assert "endings" not in replaced.get("speech_style", {})


def test_assistive_llm_is_required(client, draft):
    # 偽物に差し替えない: 作業補助の生成AIが未設定なら、作品作り用で代わりに動かさない
    resp = _import(client, draft, "女将", "create")
    assert resp.status_code == 400
    assert "作業補助" in resp.json()["detail"]


def test_invalid_targets_and_generator_failure(client, draft, fake):
    fake["generator"] = _FakeGenerator(_sketch())
    assert _import(client, draft, "", "create").status_code == 400  # 名前が無い
    assert _import(client, draft, "いない人", "create").status_code == 400  # 企画書にいない

    class _Failing:
        def generate_structured(self, *args, **kwargs):
            raise ConnectionError("connection refused")

    fake["generator"] = _Failing()
    resp = _import(client, draft, "女将", "create")
    assert resp.status_code == 502 and "connection refused" in resp.json()["detail"]
