# tests/api/test_ai_build.py
"""
Build with AI(routers/ai_build.py)の結合テスト。生成AIは偽物に差し替える。

- 工程の一覧(使えない工程も並ぶ)。使えない工程・対話での空の発言は400
- ワンショット下書きは企画書を丸ごと置き換える提案、対話は変わった項目だけの提案(空で返した項目は変えない)
- 提案は記録されるだけで下書きは変わらず、Applyで下書きに重なり、Undoで戻る。後に別の変更があればUndoは400
- 2回目からは今の工程の会話の履歴を渡す。作品のScriptwriterの文面を指示に含める(いなければプロジェクトの既定)
- 資料は、添付できれば添付し、できなければテキストにして渡す
- 生成AIの呼び出しの失敗は502で、発言を記録しない。Clearで今の工程の会話を消す
"""

import base64
import io
import zipfile

import pytest
import yaml

from core.genai import Message
from core.prompt.ai_build.common import EvidenceItem
from core.prompt.ai_build.proposal import ProposalCharacterDraft, ProposalDraft, ProposalReply
from core.service.process.genai import ai_builder
from tests.conftest import parse_yaml

MODEL = """
dramaturgy:
  title: ハチ北
  input_language: ja
  proposal:
    title: 仮の題
    logline: 古いログライン
    characters: [{name: 西谷, description: コンセルジュ}]
  agents:
    scriptwriters: [{name: 脚本家A, persona: 但馬生まれ}]
"""


def _docx(text: str) -> bytes:
    """本文が1段落だけのDOCX(Datasetに追加でき、テキストにできる最小の形)。"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.'
            'wordprocessingml.document.main+xml"/></Types>',
        )
        z.writestr(
            "word/document.xml",
            '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>",
        )
    return buffer.getvalue()


def _draft(**values) -> ProposalDraft:
    base = dict(
        title="", catchphrase="", logline="", intent="", target_area="", synopsis="", characters=[]
    )
    return ProposalDraft(**{**base, **values})


def _reply(message="了解です", has_proposal=True, **values) -> ProposalReply:
    return ProposalReply(
        message=message,
        has_proposal=has_proposal,
        proposal=_draft(**values),
        evidence=[EvidenceItem(target="企画意図", source="利用者の発言", quote="迷子")],
        questions=["対象は家族連れですか?"],
        warnings=[""],
    )


class _FakeGenerator:
    def __init__(self, reply, attach=False):
        self.reply = reply
        self.attach = attach
        self.calls = []

    def accepts_attachment(self, mime_type):
        return self.attach

    def generate_structured(self, prompt, schema, system_instruction=None, attachments=None):
        self.calls.append(
            {
                "messages": prompt,
                "schema": schema,
                "system": str(system_instruction),
                "attachments": attachments,
            }
        )
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


@pytest.fixture
def fake(monkeypatch):
    state = {"tasks": [], "generator": None}

    def build(project, task_code, config=None):
        state["tasks"].append(task_code)
        return state["generator"]

    monkeypatch.setattr(ai_builder, "build_task_text_generator", build)
    return state


@pytest.fixture
def ctx(client, project):
    pid = project.project_id
    created = parse_yaml(
        client.post(f"/projects/{pid}/drama-drafts", content="title: Dramaturgy Editor\n")
    )
    base = f"/projects/{pid}/drama-drafts/{created['draft_id']}"
    assert client.post(f"{base}/import", content=MODEL).status_code == 200
    content = parse_yaml(client.get(f"{base}/content"))
    return {
        "pid": pid,
        "draft_id": created["draft_id"],
        "base": base,
        "dramaturgy_id": content["dramaturgies"][0]["id"],
        "ai": f"/projects/{pid}/ai-build",
    }


def _send(client, ctx, mode, text="", step="proposal", refs=()):
    body = {
        "draft_id": ctx["draft_id"],
        "dramaturgy_id": ctx["dramaturgy_id"],
        "mode": mode,
        "text": text,
        "reference_file_ids": list(refs),
    }
    return client.post(
        f"{ctx['ai']}/{step}/messages", content=yaml.safe_dump(body, allow_unicode=True)
    )


def _proposal(client, ctx):
    return parse_yaml(client.get(f"{ctx['base']}/content"))["dramaturgies"][0]["proposal"]


def _messages(client, ctx, step="proposal"):
    resp = client.get(
        f"{ctx['ai']}/{step}/messages", params={"dramaturgy_id": ctx["dramaturgy_id"]}
    )
    return parse_yaml(resp)["messages"]


def _action(client, ctx, message_id, action):
    return client.post(
        f"{ctx['ai']}/messages/{message_id}/{action}", content=f"draft_id: {ctx['draft_id']}\n"
    )


def test_steps_are_listed_with_availability(client, ctx):
    steps = parse_yaml(client.get(f"{ctx['ai']}/steps"))["steps"]
    assert [(s["key"], s["available"]) for s in steps] == [
        ("proposal", True),
        ("characters", True),
        ("groups", True),
        ("relationships", True),
        ("casting", False),
    ]
    assert steps[0]["role_name"] == "scriptwriter" and steps[0]["task_code"] == "draft_proposal"


def test_one_shot_proposes_whole_proposal_and_apply_undo(client, ctx, fake):
    fake["generator"] = _FakeGenerator(
        _reply(
            title="ハチ北 スキーガイド",
            intent="迷子を減らす",
            characters=[ProposalCharacterDraft(name="西谷", description="名コンセルジュ")],
        )
    )
    resp = _send(client, ctx, "one_shot", "家族向けにしたい")
    assert resp.status_code == 200, resp.text
    reply = parse_yaml(resp)
    assert fake["tasks"] == ["draft_proposal"]
    assert reply["role"] == "assistant" and reply["proposal_status"] == "pending"
    assert reply["questions"] == ["対象は家族連れですか?"] and reply["warnings"] == []
    # 丸ごと置き換える(空で返したログラインは消す)
    assert set(reply["changed_fields"]) == {"title", "logline", "intent", "characters"}
    assert _proposal(client, ctx)["title"] == "仮の題"  # 記録しただけで、下書きは変わらない

    # 指示: Scriptwriterの文面とワンショットの指示。本文: 今の企画書と要望
    call = fake["generator"].calls[0]
    assert (
        "脚本家A" in call["system"]
        and "但馬生まれ" in call["system"]
        and "ワンショット" in call["system"]
    )
    last = call["messages"][-1]
    assert (
        isinstance(last, Message)
        and "古いログライン" in last.text
        and "家族向けにしたい" in last.text
    )

    applied = parse_yaml(_action(client, ctx, reply["id"], "apply"))
    assert applied["proposal_status"] == "applied"
    proposal = _proposal(client, ctx)
    assert (proposal["title"], proposal["intent"]) == ("ハチ北 スキーガイド", "迷子を減らす")
    assert "logline" not in proposal
    assert proposal["characters"] == [{"name": "西谷", "description": "名コンセルジュ"}]
    assert _action(client, ctx, reply["id"], "apply").status_code == 400  # 2度は反映しない

    undone = parse_yaml(_action(client, ctx, reply["id"], "undo"))
    assert undone["proposal_status"] == "undone"
    assert _proposal(client, ctx)["logline"] == "古いログライン"
    assert [m["role"] for m in _messages(client, ctx)] == ["user", "assistant"]


def test_dialogue_proposes_only_changed_items_and_passes_history(client, ctx, fake):
    fake["generator"] = _FakeGenerator(
        _reply("どんな家族ですか?", has_proposal=False, title="無視される")
    )
    first = parse_yaml(_send(client, ctx, "dialogue", "相談したい"))
    assert first["proposal"] is None and first["proposal_status"] is None

    # 空で返した項目・空の登場人物は変えない
    fake["generator"].reply = _reply("ログラインを直しました", logline="新しいログライン")
    second = parse_yaml(_send(client, ctx, "dialogue", "ログラインを考えて"))
    assert second["changed_fields"] == ["logline"]
    history = fake["generator"].calls[1]["messages"]
    assert [m.role for m in history] == ["user", "assistant", "user"]
    assert history[0].text == "相談したい" and history[1].text == "どんな家族ですか?"

    _action(client, ctx, second["id"], "apply")
    proposal = _proposal(client, ctx)
    assert (proposal["title"], proposal["logline"]) == ("仮の題", "新しいログライン")
    assert proposal["characters"] == [{"name": "西谷", "description": "コンセルジュ"}]


def test_undo_is_refused_after_another_change(client, ctx, fake):
    fake["generator"] = _FakeGenerator(_reply(logline="変更"))
    reply = parse_yaml(_send(client, ctx, "dialogue", "変えて"))
    _action(client, ctx, reply["id"], "apply")
    edit = {"dramaturgies": [{"id": ctx["dramaturgy_id"], "proposal": {"title": "手で直した"}}]}
    client.post(f"{ctx['base']}/edit", content=yaml.safe_dump(edit, allow_unicode=True))
    assert _action(client, ctx, reply["id"], "undo").status_code == 400


def test_errors_and_clear(client, ctx, fake):
    assert _send(client, ctx, "dialogue", "").status_code == 400  # 対話では空の発言を断る
    assert (
        _send(client, ctx, "dialogue", "x", step="casting").status_code == 400
    )  # まだ使えない工程
    assert _action(client, ctx, 9999, "apply").status_code == 404

    fake["generator"] = _FakeGenerator(RuntimeError("接続できない"))
    assert _send(client, ctx, "dialogue", "相談").status_code == 502
    assert _messages(client, ctx) == []  # 失敗した発言は記録しない

    fake["generator"] = _FakeGenerator(_reply(has_proposal=False))
    _send(client, ctx, "dialogue", "相談")
    resp = client.delete(
        f"{ctx['ai']}/proposal/messages", params={"dramaturgy_id": ctx["dramaturgy_id"]}
    )
    assert parse_yaml(resp)["deleted"] == 2
    assert _messages(client, ctx) == []


def test_references_are_attached_or_converted(client, ctx, fake):
    upload = {
        "filename": "guide.docx",
        "content_base64": base64.b64encode(_docx("宿屋エリアとゲレンデ")).decode(),
    }
    file_id = parse_yaml(client.post(f"/projects/{ctx['pid']}/datasets/files", json=upload))[
        "file_id"
    ]

    fake["generator"] = _FakeGenerator(_reply(has_proposal=False), attach=True)
    _send(client, ctx, "dialogue", "資料を見て", refs=[file_id])
    call = fake["generator"].calls[0]
    assert len(call["attachments"]) == 1
    assert (
        "guide.docx" in call["messages"][-1].text and "宿屋エリア" not in call["messages"][-1].text
    )

    fake["generator"] = _FakeGenerator(_reply(has_proposal=False), attach=False)
    resp = _send(client, ctx, "dialogue", "資料を見て", refs=[file_id])
    assert resp.status_code == 200, resp.text
    call = fake["generator"].calls[0]
    assert (
        call["attachments"] == []
        and "## guide.docx\n宿屋エリアとゲレンデ" in call["messages"][-1].text
    )


def test_scriptwriter_falls_back_to_project_default(client, project, fake):
    pid = project.project_id
    created = parse_yaml(
        client.post(f"/projects/{pid}/drama-drafts", content="title: Dramaturgy Editor\n")
    )
    base = f"/projects/{pid}/drama-drafts/{created['draft_id']}"
    client.post(f"{base}/import", content="dramaturgy: {title: エージェントのいない作品}\n")
    did = parse_yaml(client.get(f"{base}/content"))["dramaturgies"][0]["id"]
    fake["generator"] = _FakeGenerator(_reply(has_proposal=False))
    body = {
        "draft_id": created["draft_id"],
        "dramaturgy_id": did,
        "mode": "dialogue",
        "text": "相談",
    }
    resp = client.post(
        f"/projects/{pid}/ai-build/proposal/messages",
        content=yaml.safe_dump(body, allow_unicode=True),
    )
    assert resp.status_code == 200, resp.text
    assert "脚本家" in fake["generator"].calls[0]["system"]


def test_unreadable_reference_is_a_bad_request(client, ctx, fake):
    broken = _docx("x").replace(b"<w:t>x</w:t>", b"<w:t>x</w:t")  # 本文のXMLが壊れたDOCX
    upload = {"filename": "broken.docx", "content_base64": base64.b64encode(broken).decode()}
    file_id = parse_yaml(client.post(f"/projects/{ctx['pid']}/datasets/files", json=upload))[
        "file_id"
    ]
    fake["generator"] = _FakeGenerator(_reply(has_proposal=False), attach=False)
    resp = _send(client, ctx, "dialogue", "資料を見て", refs=[file_id])
    assert resp.status_code == 400 and "broken.docx" in resp.text
    assert _messages(client, ctx) == []
