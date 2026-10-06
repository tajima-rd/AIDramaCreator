# tests/api/test_ai_build_synopsis.py
"""
Build with AIのあらすじの工程(Synopsis)の結合テスト。生成AIは偽物に差し替える(提供元を呼ばない)。

- 作品全体のあらすじと、今ある幕の題・あらすじを更新する(幕は番号で指す)。幕は増やさない(無い番号は外して注意)。
  空の値では既存の値を消さない
- 対話で提案が無ければ、反映するものは無い
- 生成AIには企画書・登場人物・場所・今の幕とそのシーンを渡し、会話の履歴には過去の提案の中身を添える
"""

import pytest

from core.prompt.ai_build.synopsis import ActSynopsisDraft, SynopsisReply
from tests.api.test_ai_build import _action, _FakeGenerator, _messages, _send, fake  # noqa: F401  (fakeはfixture)
from tests.conftest import parse_yaml

WORLD = """
characters:
  - {key: nishitani, name: 西谷, gender: 男性, age: 50代}
locations:
  - {key: lift, name: 第1リフト, instruction: リフト券の買い方を案内する, description: 山頂へ向かうリフト}
dramaturgy:
  title: ハチ北
  input_language: ja
  synopsis: 古いあらすじ
  proposal: {title: ハチ北 スキーガイド, intent: スキー場の魅力を伝える}
  characters: [{ref: nishitani}]
  locations: [{ref: lift}]
  acts:
    - order: 0
      title: 出会い
      synopsis: 第1幕の古いあらすじ
      scenes:
        - {order: 0, title: リフト乗り場, synopsis: 西谷が客を迎える, location: {ref: lift}}
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


def _reply(has_proposal=True, synopsis="", acts=()):
    return SynopsisReply(
        message="書きました",
        has_proposal=has_proposal,
        synopsis=synopsis,
        acts=list(acts),
        evidence=[],
        questions=[],
        warnings=[],
    )


def _dramaturgy(client, ctx):
    return parse_yaml(client.get(f"{ctx['base']}/content"))["dramaturgies"][0]


def _acts(client, ctx):
    return sorted(_dramaturgy(client, ctx)["acts"], key=lambda a: a["order"])


def test_one_shot_updates_dramaturgy_and_act_synopses(client, ctx, fake):
    fake["generator"] = _FakeGenerator(
        _reply(
            synopsis="新しいあらすじ",
            acts=[
                ActSynopsisDraft(number=1, title="", synopsis="第1幕の新しいあらすじ"),
                ActSynopsisDraft(number=2, title="別れ", synopsis="第2幕のあらすじ"),
                ActSynopsisDraft(number=3, title="無い幕", synopsis="作らない"),
            ],
        )
    )
    resp = _send(client, ctx, "one_shot", step="synopsis")
    assert resp.status_code == 200, resp.text
    message = parse_yaml(resp)
    assert fake["tasks"] == ["write_synopsis"]
    assert message["changed_fields"] == [
        "作品全体のあらすじ",
        "第1幕のあらすじ",
        "第2幕の題",
        "第2幕のあらすじ",
    ]
    assert "第3幕はありません" in " ".join(message["warnings"])
    # 生成AIには企画書・登場人物・場所・今の幕とそのシーンを渡す
    request = fake["generator"].calls[0]["messages"][-1].text
    for text in ("スキー場の魅力を伝える", "西谷", "山頂へ向かうリフト", "リフト券の買い方を案内する", "第1幕の古いあらすじ", "西谷が客を迎える"):
        assert text in request

    assert _action(client, ctx, message["id"], "apply").status_code == 200
    dramaturgy = _dramaturgy(client, ctx)
    assert dramaturgy["synopsis"] == "新しいあらすじ"
    acts = _acts(client, ctx)
    assert len(acts) == 2  # 幕は増えない
    # 空で返した題は変えない
    assert (acts[0]["title"], acts[0]["synopsis"]) == ("出会い", "第1幕の新しいあらすじ")
    assert (acts[1]["title"], acts[1]["synopsis"]) == ("別れ", "第2幕のあらすじ")
    # シーンはそのまま
    assert acts[0]["scenes"][0]["synopsis"] == "西谷が客を迎える"

    assert _action(client, ctx, message["id"], "undo").status_code == 200
    assert _dramaturgy(client, ctx)["synopsis"] == "古いあらすじ"


def test_dialogue_without_proposal_changes_nothing(client, ctx, fake):
    fake["generator"] = _FakeGenerator(_reply(has_proposal=False, synopsis="使わない"))
    resp = _send(client, ctx, "dialogue", text="第2幕はどうしたらよい?", step="synopsis")
    assert resp.status_code == 200, resp.text
    message = parse_yaml(resp)
    assert message["proposal"] is None and message["proposal_status"] is None


def test_history_includes_previous_synopsis_proposal(client, ctx, fake):
    fake["generator"] = _FakeGenerator(
        _reply(synopsis="提案したあらすじ", acts=[ActSynopsisDraft(number=2, title="別れ", synopsis="")])
    )
    assert _send(client, ctx, "dialogue", text="案を出して", step="synopsis").status_code == 200
    assert _send(client, ctx, "dialogue", text="もう少し短く", step="synopsis").status_code == 200
    history = fake["generator"].calls[1]["messages"]
    assistant = next(m for m in history if m.role == "assistant")
    assert "提案したあらすじ" in assistant.text and "第2幕: 別れ" in assistant.text
    # 会話は工程ごと
    assert len(_messages(client, ctx, step="synopsis")) == 4
    assert _messages(client, ctx, step="proposal") == []
