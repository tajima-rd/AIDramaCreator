# tests/api/test_ai_build_direction.py
"""
Build with AIの演出付きの原稿の工程(Direction)の結合テスト。生成AIは偽物に差し替える(提供元を呼ばない)。

- 選んだシーンの台詞の1行ごとに、演出付きの台詞(Dialogue)を作る(台詞・配役と対応付ける)。2回目からは識別子を保って書き換える
- 音声にする文は、感情タグを除くと台詞の文言と同じでなければならない(違えば台詞のまま使い注意)。一覧に無い感情タグは外す
- 演出の無い台詞は、今の原稿を残す(無ければ台詞のままの原稿を作る)。無い番号は外して注意
- 訳文は、音声の言語が制作の言語と違う作品だけ(無ければ注意)
- 台詞の無いシーンは断る
"""

import pytest
import yaml

from core.prompt.ai_build.direction import DialogueDirectionDraft, DirectionReply
from tests.api.test_ai_build import _action, _FakeGenerator, fake  # noqa: F401  (fakeはfixture)
from tests.conftest import parse_yaml

WORLD = """
characters:
  - {key: nishitani, name: 西谷, age: 50代}
  - {key: guest, name: 客}
dramaturgy:
  title: ハチ北
  input_language: ja
  output_language: zh
  characters: [{ref: nishitani}, {ref: guest}]
  casts:
    - {key: nishitani_cast, character: {ref: nishitani}, accent: 関西弁}
    - {key: guest_cast, character: {ref: guest}}
  acts:
    - order: 0
      scenes:
        - order: 0
          title: リフト乗り場
          synopsis: 西谷が客を迎える
          script:
            lines:
              - {order: 0, cast: {ref: nishitani_cast}, text: ようこそ、ハチ北へ。}
              - {order: 1, cast: {ref: guest_cast}, text: よろしくお願いします。}
              - {order: 2, cast: {ref: nishitani_cast}, text: ほな、行こか。}
        - {order: 1, title: 台詞なし}
"""


@pytest.fixture
def ctx(client, project):
    pid = project.project_id
    created = parse_yaml(client.post(f"/projects/{pid}/drama-drafts", content="title: Dramaturgy Editor\n"))
    base = f"/projects/{pid}/drama-drafts/{created['draft_id']}"
    resp = client.post(f"{base}/import", content=WORLD)
    assert resp.status_code == 200, resp.text
    dramaturgy = parse_yaml(client.get(f"{base}/content"))["dramaturgies"][0]
    scenes = sorted(dramaturgy["acts"][0]["scenes"], key=lambda s: s["order"])
    return {
        "pid": pid,
        "draft_id": created["draft_id"],
        "base": base,
        "dramaturgy_id": dramaturgy["id"],
        "scene_ids": [s["id"] for s in scenes],
        "ai": f"/projects/{pid}/ai-build",
    }


def _draft(number, text, **values):
    base = dict(action="", style="", pace="", dynamics="", emotion="", pause_after="", translated_text="")
    return DialogueDirectionDraft(number=number, text=text, **{**base, **values})


def _reply(dialogues=(), has_proposal=True):
    return DirectionReply(
        message="演出しました", has_proposal=has_proposal, dialogues=list(dialogues), evidence=[], questions=[], warnings=[]
    )


def _send(client, ctx, mode="one_shot", scene_index=0, text=""):
    body = {
        "draft_id": ctx["draft_id"],
        "dramaturgy_id": ctx["dramaturgy_id"],
        "scene_id": ctx["scene_ids"][scene_index],
        "mode": mode,
        "text": text,
        "reference_file_ids": [],
    }
    return client.post(f"{ctx['ai']}/direction/messages", content=yaml.safe_dump(body, allow_unicode=True))


def _elements(client, ctx):
    dramaturgy = parse_yaml(client.get(f"{ctx['base']}/content"))["dramaturgies"][0]
    scene = next(s for s in dramaturgy["acts"][0]["scenes"] if s["id"] == ctx["scene_ids"][0])
    lines = {line["key"]: line for line in scene["script"]["lines"]}
    elements = sorted(scene.get("elements") or [], key=lambda e: e["order"])
    return [(lines[e["line"]["ref"]]["text"], e) for e in elements]


def test_one_shot_creates_directed_dialogues(client, ctx, fake):
    fake["generator"] = _FakeGenerator(
        _reply(
            [
                _draft(1, "[excited] ようこそ、ハチ北へ。[angry]", action="Waves", style="Warm", pace="Moderate",
                       emotion="Glad", translated_text="[excited] 欢迎来到八北。"),
                _draft(2, "どうぞよろしくお願いします。", style="Polite"),
                _draft(9, "無い台詞"),
            ]
        )
    )
    resp = _send(client, ctx)
    assert resp.status_code == 200, resp.text
    message = parse_yaml(resp)
    assert fake["tasks"] == ["direct_scene"]
    assert message["changed_fields"] == ["3行の台詞に演出を付ける(新しく3行)"]
    warnings = " ".join(message["warnings"])
    for text in ("「[angry]」は使えない", "台詞2の音声にする文が台詞の文言と違う", "台詞9はありません", "台詞3の演出が無い", "台詞2の訳文がありません"):
        assert text in warnings
    # 生成AIには、話す人物の配役(訛り)・番号付きの台詞・訳すことを渡す
    request = fake["generator"].calls[0]["messages"][-1].text
    for text in ("訛り: 関西弁", "1. 西谷: ようこそ、ハチ北へ。", "3. 西谷: ほな、行こか。", "音声の言語: zh。訳文を作る"):
        assert text in request
    assert "[whispers]" in fake["generator"].calls[0]["system"]

    assert _action(client, ctx, message["id"], "apply").status_code == 200
    elements = _elements(client, ctx)
    assert [line for line, _ in elements] == ["ようこそ、ハチ北へ。", "よろしくお願いします。", "ほな、行こか。"]
    first, second, third = (e for _, e in elements)
    assert first["text"] == "[excited] ようこそ、ハチ北へ。" and first["action"] == "Waves"
    assert first["direction"] == {"style": "Warm", "pace": "Moderate", "emotion": "Glad"}
    assert first["translated_text"] == "[excited] 欢迎来到八北。"
    # 文言を変えた台詞・演出の無い台詞は、台詞のまま
    assert second["text"] == "よろしくお願いします。" and second["direction"] == {"style": "Polite"}
    assert third["text"] == "ほな、行こか。" and first["cast"] != second["cast"]

    assert _action(client, ctx, message["id"], "undo").status_code == 200
    assert _elements(client, ctx) == []


def test_second_proposal_rewrites_elements_keeping_ids(client, ctx, fake):
    fake["generator"] = _FakeGenerator(
        _reply([_draft(n, "", action="Smiles") for n in (1, 2, 3)])
    )
    first = parse_yaml(_send(client, ctx))
    assert _action(client, ctx, first["id"], "apply").status_code == 200
    ids = [e["id"] for _, e in _elements(client, ctx)]

    fake["generator"] = _FakeGenerator(_reply([_draft(2, "[whispers] よろしくお願いします。")]))
    second = parse_yaml(_send(client, ctx, mode="dialogue", text="2行目はささやいて"))
    assert second["changed_fields"] == ["1行の台詞に演出を付ける"]
    assert _action(client, ctx, second["id"], "apply").status_code == 200
    elements = [e for _, e in _elements(client, ctx)]
    assert [e["id"] for e in elements] == ids
    # 返した行は丸ごと書き換え(空のト書きは消える)、返さなかった行は残る
    assert elements[1]["text"] == "[whispers] よろしくお願いします。" and "action" not in elements[1]
    assert elements[0]["action"] == "Smiles"


def test_scene_without_lines_is_refused_and_script_is_locked_after_direction(client, ctx, fake):
    fake["generator"] = _FakeGenerator(_reply([_draft(1, "")]))
    resp = _send(client, ctx, scene_index=1)
    assert resp.status_code == 400 and "台詞がありません" in resp.text
    message = parse_yaml(_send(client, ctx))
    assert _action(client, ctx, message["id"], "apply").status_code == 200
    # 原稿ができたシーンの台詞は、Scriptの工程では書き換えない
    body = {"draft_id": ctx["draft_id"], "dramaturgy_id": ctx["dramaturgy_id"], "scene_id": ctx["scene_ids"][0], "mode": "one_shot"}
    resp = client.post(f"{ctx['ai']}/script/messages", content=yaml.safe_dump(body))
    assert resp.status_code == 400 and "演出付きの原稿" in resp.text


def test_same_language_work_has_no_translation(client, ctx, fake):
    patch = {"dramaturgies": [{"id": ctx["dramaturgy_id"], "output_language": "ja"}]}
    assert client.post(f"{ctx['base']}/edit", content=yaml.safe_dump(patch)).status_code == 200
    fake["generator"] = _FakeGenerator(_reply([_draft(n, "", translated_text="訳さない") for n in (1, 2, 3)]))
    message = parse_yaml(_send(client, ctx))
    assert "訳文" not in " ".join(message["warnings"])
    assert "訳さない" in fake["generator"].calls[0]["messages"][-1].text
    assert _action(client, ctx, message["id"], "apply").status_code == 200
    assert all("translated_text" not in e for _, e in _elements(client, ctx))
