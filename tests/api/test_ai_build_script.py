# tests/api/test_ai_build_script.py
"""
Build with AIの読み上げ台本の工程(Script)の結合テスト。生成AIは偽物に差し替える(提供元を呼ばない)。

- 選んだシーンの台詞の全体を置き換える(今の行を順に書き換え、余った行は消し、足りない行は足す)。話者は配役の人物だけ
  (配役にいない人物の行・空の行は外して注意)
- 会話はシーンごとに分ける(送る・見せる・消すにはシーンが要る)
- 生成AIには、シーンの設定・前後のシーン・話せる人物と配役・今の台詞を渡す。配役が無い・演出付きの原稿があるシーンは断る
"""

import pytest
import yaml

from core.prompt.ai_build.script import LineDraft, ScriptReply
from tests.api.test_ai_build import _action, _FakeGenerator, _send, fake  # noqa: F401  (fakeはfixture)
from tests.conftest import parse_yaml

WORLD = """
characters:
  - {key: nishitani, name: 西谷, speech_style: {first_person: わし}}
  - {key: guest, name: 客}
  - {key: father, name: 父}
locations:
  - {key: lift, name: 第1リフト, instruction: リフト券の買い方を案内する}
dramaturgy:
  title: ハチ北
  input_language: ja
  synopsis: 西谷が客を山頂へ案内する
  characters: [{ref: nishitani}, {ref: guest}, {ref: father}]
  locations: [{ref: lift}]
  casts:
    - {key: nishitani_cast, character: {ref: nishitani}, performance: {title: 頼れる案内役}}
    - {key: guest_cast, character: {ref: guest}}
  acts:
    - order: 0
      synopsis: 出会いの幕
      scenes:
        - order: 0
          title: 駅
          synopsis: 客が駅に着く
          script:
            lines:
              - {order: 0, cast: {ref: guest_cast}, text: 着いた}
        - order: 1
          title: リフト乗り場
          synopsis: 西谷が客を迎える
          location: {ref: lift}
          script:
            lines:
              - {order: 0, cast: {ref: nishitani_cast}, text: 古い台詞1}
              - {order: 1, cast: {ref: guest_cast}, text: 古い台詞2}
              - {order: 2, cast: {ref: nishitani_cast}, text: 古い台詞3}
        - {order: 2, title: 山頂, synopsis: 山頂で景色を見る}
        - order: 3
          title: 演出済み
          elements:
            - {type: sound_effect, order: 0}
"""


@pytest.fixture
def ctx(client, project):
    pid = project.project_id
    created = parse_yaml(client.post(f"/projects/{pid}/drama-drafts", content="title: Dramaturgy Editor\n"))
    base = f"/projects/{pid}/drama-drafts/{created['draft_id']}"
    resp = client.post(f"{base}/import", content=WORLD)
    assert resp.status_code == 200, resp.text
    content = parse_yaml(client.get(f"{base}/content"))
    dramaturgy = content["dramaturgies"][0]
    scenes = sorted(dramaturgy["acts"][0]["scenes"], key=lambda s: s["order"])
    return {
        "pid": pid,
        "draft_id": created["draft_id"],
        "base": base,
        "dramaturgy_id": dramaturgy["id"],
        "scene_ids": [s["id"] for s in scenes],
        "ai": f"/projects/{pid}/ai-build",
    }


def _reply(lines=(), has_proposal=True):
    return ScriptReply(
        message="書きました", has_proposal=has_proposal, lines=list(lines), evidence=[], questions=[], warnings=[]
    )


def _send_scene(client, ctx, mode, scene_index, text=""):
    body = {
        "draft_id": ctx["draft_id"],
        "dramaturgy_id": ctx["dramaturgy_id"],
        "scene_id": ctx["scene_ids"][scene_index],
        "mode": mode,
        "text": text,
        "reference_file_ids": [],
    }
    return client.post(f"{ctx['ai']}/script/messages", content=yaml.safe_dump(body, allow_unicode=True))


def _lines(client, ctx, scene_index):
    content = parse_yaml(client.get(f"{ctx['base']}/content"))
    names = {c["key"]: c["name"] for c in content["characters"]}
    dramaturgy = content["dramaturgies"][0]
    casts = {c["key"]: names[c["character"]["ref"]] for c in dramaturgy["casts"]}
    scene = next(s for s in dramaturgy["acts"][0]["scenes"] if s["id"] == ctx["scene_ids"][scene_index])
    lines = sorted((scene.get("script") or {}).get("lines") or [], key=lambda line: line["order"])
    return [(line["id"], casts[line["cast"]["ref"]], line["text"]) for line in lines]


def test_one_shot_replaces_scene_script(client, ctx, fake):
    before = _lines(client, ctx, 1)
    fake["generator"] = _FakeGenerator(
        _reply(
            [
                LineDraft(speaker="西谷", text="ようこそ"),
                LineDraft(speaker="父", text="配役が無い"),
                LineDraft(speaker="客", text=""),
                LineDraft(speaker="客", text="リフト券はどこで?"),
            ]
        )
    )
    resp = _send_scene(client, ctx, "one_shot", 1)
    assert resp.status_code == 200, resp.text
    message = parse_yaml(resp)
    assert fake["tasks"] == ["write_dialogue"]
    assert message["scene_id"] == ctx["scene_ids"][1]
    assert message["changed_fields"] == ["台詞を2行にする(今は3行)"]
    assert "「父」は配役にいない" in " ".join(message["warnings"])
    # 画面に出す提案は、反映する行だけ
    assert message["proposal"] == {"lines": [{"speaker": "西谷", "text": "ようこそ"}, {"speaker": "客", "text": "リフト券はどこで?"}]}
    # 生成AIには前後のシーン・シーンの場所の案内・話せる人物と配役・今の台詞を渡す
    request = fake["generator"].calls[0]["messages"][-1].text
    for text in ("客が駅に着く", "客: 着いた", "山頂で景色を見る", "リフト券の買い方を案内する", "頼れる案内役", "わし", "西谷: 古い台詞1"):
        assert text in request
    assert "# 話せる人物の設定" in request and "# 父" not in request.split("# 話せる人物の設定")[1]

    assert _action(client, ctx, message["id"], "apply").status_code == 200
    after = _lines(client, ctx, 1)
    assert [(speaker, text) for _, speaker, text in after] == [("西谷", "ようこそ"), ("客", "リフト券はどこで?")]
    # 今の行は識別子を保って書き換え、余った行は消す
    assert [line_id for line_id, _, _ in after] == [line_id for line_id, _, _ in before[:2]]
    # ほかのシーンは変わらない
    assert [(s, t) for _, s, t in _lines(client, ctx, 0)] == [("客", "着いた")]

    assert _action(client, ctx, message["id"], "undo").status_code == 200
    assert _lines(client, ctx, 1) == before


def test_new_lines_are_added_to_empty_scene(client, ctx, fake):
    fake["generator"] = _FakeGenerator(
        _reply([LineDraft(speaker="西谷", text="山頂だ"), LineDraft(speaker="客", text="きれい")])
    )
    message = parse_yaml(_send_scene(client, ctx, "one_shot", 2))
    assert message["changed_fields"] == ["台詞を2行にする"]
    assert _action(client, ctx, message["id"], "apply").status_code == 200
    assert [(s, t) for _, s, t in _lines(client, ctx, 2)] == [("西谷", "山頂だ"), ("客", "きれい")]


def test_messages_are_separated_by_scene(client, ctx, fake):
    fake["generator"] = _FakeGenerator(_reply(has_proposal=False))
    assert _send_scene(client, ctx, "dialogue", 1, text="どう始める?").status_code == 200
    assert _send_scene(client, ctx, "dialogue", 2, text="山頂は?").status_code == 200
    # 2回目の生成AIには、そのシーンの履歴だけを渡す
    assert len(fake["generator"].calls[1]["messages"]) == 1

    def listed(index):
        params = {"dramaturgy_id": ctx["dramaturgy_id"], "scene_id": ctx["scene_ids"][index]}
        return parse_yaml(client.get(f"{ctx['ai']}/script/messages", params=params))["messages"]

    assert [m["text"] for m in listed(1)] == ["どう始める?", "書きました"]
    assert [m["text"] for m in listed(2)] == ["山頂は?", "書きました"]
    params = {"dramaturgy_id": ctx["dramaturgy_id"], "scene_id": ctx["scene_ids"][1]}
    assert parse_yaml(client.delete(f"{ctx['ai']}/script/messages", params=params))["deleted"] == 2
    assert listed(1) == [] and len(listed(2)) == 2
    # シーンを選ばなければ断る
    resp = client.get(f"{ctx['ai']}/script/messages", params={"dramaturgy_id": ctx["dramaturgy_id"]})
    assert resp.status_code == 400


def test_scene_with_elements_or_without_casts_is_refused(client, ctx, fake):
    fake["generator"] = _FakeGenerator(_reply([LineDraft(speaker="西谷", text="使わない")]))
    resp = _send_scene(client, ctx, "one_shot", 3)
    assert resp.status_code == 400 and "演出付きの原稿" in resp.text
    # 配役が無ければ断る
    dramaturgy = parse_yaml(client.get(f"{ctx['base']}/content"))["dramaturgies"][0]
    casts = [{"id": c["id"], "delete": True} for c in dramaturgy["casts"]]
    lines = [
        {"id": s["id"], "script": {"lines": [{"id": line["id"], "delete": True} for line in s["script"]["lines"]]}}
        for s in dramaturgy["acts"][0]["scenes"]
        if (s.get("script") or {}).get("lines")
    ]
    patch = {"dramaturgies": [{"id": ctx["dramaturgy_id"], "acts": [{"id": dramaturgy["acts"][0]["id"], "scenes": lines}], "casts": casts}]}
    assert client.post(f"{ctx['base']}/edit", content=yaml.safe_dump(patch, allow_unicode=True)).status_code == 200
    resp = _send_scene(client, ctx, "one_shot", 2)
    assert resp.status_code == 400 and "配役がありません" in resp.text
    # どちらも生成AIを呼ばない
    assert fake["generator"].calls == []
