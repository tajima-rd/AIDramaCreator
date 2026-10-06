# tests/api/test_ai_build_scenes.py
"""
Build with AIのシーンのあらすじの工程(Scenes)の結合テスト。生成AIは偽物に差し替える(提供元を呼ばない)。

- 今あるシーンの題・あらすじを更新する(シーンは幕とシーンの番号で指す)。シーンは増やさない(無い番号は外して注意)。
  場所は変えない。空の値では既存の値を消さない
- 生成AIには作品と幕のあらすじ・シーンの場所(住所・案内すること・事実)・状況を渡し、会話の履歴には過去の提案の中身を添える
"""

import pytest

from core.prompt.ai_build.scene_synopsis import SceneSynopsisDraft, SceneSynopsisReply
from tests.api.test_ai_build import _action, _FakeGenerator, _send, fake  # noqa: F401  (fakeはfixture)
from tests.conftest import parse_yaml

WORLD = """
characters:
  - {key: nishitani, name: 西谷}
locations:
  - {key: lift, name: 第1リフト, address: 香美町村岡区大笹, instruction: リフト券の買い方を案内する, description: 山頂へ向かうリフト}
dramaturgy:
  title: ハチ北
  input_language: ja
  synopsis: 西谷が客を山頂へ案内する
  characters: [{ref: nishitani}]
  locations: [{ref: lift}]
  acts:
    - order: 0
      synopsis: 出会いの幕
      scenes:
        - {order: 0, title: リフト乗り場, synopsis: 古いシーンのあらすじ, location: {ref: lift}, situation: {time_of_day: 朝}}
        - {order: 1}
    - order: 1
"""


@pytest.fixture
def ctx(client, project):
    pid = project.project_id
    created = parse_yaml(client.post(f"/projects/{pid}/drama-drafts", content="title: Dramaturgy Editor\n"))
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


def _reply(scenes=(), has_proposal=True):
    return SceneSynopsisReply(
        message="書きました", has_proposal=has_proposal, scenes=list(scenes), evidence=[], questions=[], warnings=[]
    )


def _scenes(client, ctx):
    acts = parse_yaml(client.get(f"{ctx['base']}/content"))["dramaturgies"][0]["acts"]
    act = next(a for a in acts if a["order"] == 0)
    return sorted(act["scenes"], key=lambda s: s["order"]), acts


def test_one_shot_updates_scene_titles_and_synopses(client, ctx, fake):
    fake["generator"] = _FakeGenerator(
        _reply(
            [
                SceneSynopsisDraft(act=1, scene=1, title="", synopsis="新しいシーンのあらすじ"),
                SceneSynopsisDraft(act=1, scene=2, title="山頂", synopsis="山頂で景色を見る"),
                SceneSynopsisDraft(act=1, scene=3, title="無いシーン", synopsis="作らない"),
                SceneSynopsisDraft(act=2, scene=1, title="無いシーン", synopsis="第2幕にはシーンが無い"),
                SceneSynopsisDraft(act=5, scene=1, title="無い幕", synopsis="作らない"),
            ]
        )
    )
    resp = _send(client, ctx, "one_shot", step="scenes")
    assert resp.status_code == 200, resp.text
    message = parse_yaml(resp)
    assert fake["tasks"] == ["write_synopsis"]
    assert message["changed_fields"] == [
        "第1幕のシーン1のあらすじ",
        "第1幕のシーン2の題",
        "第1幕のシーン2のあらすじ",
    ]
    warnings = " ".join(message["warnings"])
    assert "第1幕のシーン3はありません" in warnings and "第2幕のシーン1はありません" in warnings
    assert "第5幕はありません" in warnings
    # 生成AIには作品と幕のあらすじ・シーンの場所と状況を渡す
    request = fake["generator"].calls[0]["messages"][-1].text
    for text in ("西谷が客を山頂へ案内する", "出会いの幕", "時間帯: 朝", "古いシーンのあらすじ"):
        assert text in request
    # シーンの場所の住所・案内すること・事実も渡す
    scene_part = request.split("# 今のシーン")[1]
    for text in ("住所: 香美町村岡区大笹", "この場所で案内すること: リフト券の買い方を案内する", "この場所の事実: 山頂へ向かうリフト"):
        assert text in scene_part

    assert _action(client, ctx, message["id"], "apply").status_code == 200
    scenes, acts = _scenes(client, ctx)
    assert len(scenes) == 2 and not any(a.get("scenes") for a in acts if a["order"] == 1)  # シーンは増えない
    # 空で返した題は変えず、場所はそのまま
    assert (scenes[0]["title"], scenes[0]["synopsis"]) == ("リフト乗り場", "新しいシーンのあらすじ")
    locations = {l["key"]: l["name"] for l in parse_yaml(client.get(f"{ctx['base']}/content"))["locations"]}
    assert locations[scenes[0]["location"]["ref"]] == "第1リフト"
    assert (scenes[1]["title"], scenes[1]["synopsis"]) == ("山頂", "山頂で景色を見る")

    assert _action(client, ctx, message["id"], "undo").status_code == 200
    assert _scenes(client, ctx)[0][0]["synopsis"] == "古いシーンのあらすじ"


def test_dialogue_without_proposal_changes_nothing(client, ctx, fake):
    fake["generator"] = _FakeGenerator(_reply(has_proposal=False))
    resp = _send(client, ctx, "dialogue", text="シーン2はどうする?", step="scenes")
    assert resp.status_code == 200, resp.text
    message = parse_yaml(resp)
    assert message["proposal"] is None and message["proposal_status"] is None


def test_history_includes_previous_scene_proposal(client, ctx, fake):
    fake["generator"] = _FakeGenerator(_reply([SceneSynopsisDraft(act=1, scene=2, title="山頂", synopsis="提案したあらすじ")]))
    assert _send(client, ctx, "dialogue", text="案を出して", step="scenes").status_code == 200
    assert _send(client, ctx, "dialogue", text="もう少し短く", step="scenes").status_code == 200
    assistant = next(m for m in fake["generator"].calls[1]["messages"] if m.role == "assistant")
    assert "第1幕のシーン2: 山頂" in assistant.text and "提案したあらすじ" in assistant.text
