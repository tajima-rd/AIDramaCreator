# tests/api/test_ai_build_casting.py
"""
Build with AIの配役の工程(Casting・Audition)と、声の一覧(GET /projects/{id}/voices)の結合テスト。
生成AIと声の一覧の取得は偽物に差し替える(提供元を呼ばない)。

- Casting: 配役を人物の名前で対応付けて追加・更新する(削除しない、空の値では消さない)。いない人物・決まりに無い値は外して注意。
  配役した人物は作品の登場人物に加える
- Audition: 配役ごとの演者に、声(話者)と音声合成の提供元・モデルを入れる(演者がいなければ作る)。一覧に無い声は外して注意。
  声の一覧は作品の言語で絞り込む。作品の言語が無ければ断る
"""

import pytest

from core.genai import VoiceInfo
from core.prompt.ai_build.casting import AuditionReply, CastDraft, CastingReply, VoiceChoice
from core.service.process.genai import voice_catalog
from tests.api.test_ai_build import _action, _FakeGenerator, _send, fake  # noqa: F401  (fakeはfixture)
from tests.conftest import parse_yaml

WORLD = """
characters:
  - {key: nishitani, name: 西谷, gender: 男性, age: 50代}
  - {key: father, name: 父}
  - {key: guest, name: 宿の客}
dramaturgy:
  title: ハチ北
  output_language: ja
  characters: [{ref: nishitani}, {ref: father}]
  casts:
    - key: nishitani_cast
      character: {ref: nishitani}
      performance: {title: 名コンセルジュ, pace: ゆっくり}
      voice_gender: male
"""

VOICES = [
    VoiceInfo("ja-jp-advisor-1", "Authoritative Advisor 1", "ja-JP", "male", "low", "Osaka Japanese", "Advisor", None, "44-year-old"),
    VoiceInfo("ja-jp-tutor-1", "Tutor 1", "ja-JP", "female", "high", "Tokyo Japanese", "Tutor", None, "30-year-old"),
    VoiceInfo("kore", "Kore", "en-US", "female", "middle", "General American", None, None, "Firm"),
]


@pytest.fixture
def ctx(client, project, monkeypatch):
    pid = project.project_id
    tts = {"tts": {"client": "Gemini", "model": "gemini-3.8-flash-lite-tts"}}
    assert client.put(f"/projects/{pid}/preferences", json=tts).status_code == 200
    calls = []

    def list_voices(project, language=None):
        calls.append(language)
        return [v for v in VOICES if voice_catalog.matches_language(v, language)]

    monkeypatch.setattr(voice_catalog, "list_voices", list_voices)
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
        "voice_calls": calls,
    }


def _reply(cls, has_proposal=True, **lists):
    return cls(message="決めました", has_proposal=has_proposal, evidence=[], questions=[], warnings=[], **lists)


def _cast(character, **values):
    base = dict(billing="", performance_title="", performance_description="", pace="", voice_gender="", language="", accent="")
    return CastDraft(character=character, **{**base, **values})


def _dramaturgy(client, ctx):
    return parse_yaml(client.get(f"{ctx['base']}/content"))["dramaturgies"][0]


def _names(client, ctx):
    content = parse_yaml(client.get(f"{ctx['base']}/content"))
    return {c["key"]: c["name"] for c in content["characters"]}


def test_casting_adds_and_updates_casts(client, ctx, fake):
    fake["generator"] = _FakeGenerator(
        _reply(
            CastingReply,
            casts=[
                _cast("西谷", billing="lead", performance_description="落ち着いた低い声", pace=""),
                _cast("宿の客", billing="minor", voice_gender="x", accent="関西弁"),
                _cast("いない人", billing="supporting"),
            ],
        )
    )
    resp = _send(client, ctx, "one_shot", step="casting")
    assert resp.status_code == 200, resp.text
    message = parse_yaml(resp)
    assert fake["tasks"] == ["cast_character"]
    assert "いない人" in " ".join(message["warnings"]) and "声の性別「x」" in " ".join(message["warnings"])
    assert "「宿の客」の配役を追加(端役)" in message["changed_fields"]
    # 生成AIには登場人物の設定と今の配役を渡す
    request = fake["generator"].calls[0]["messages"][-1].text
    assert "西谷" in request and "名コンセルジュ" in request

    assert _action(client, ctx, message["id"], "apply").status_code == 200
    dramaturgy = _dramaturgy(client, ctx)
    names = _names(client, ctx)
    casts = {names[c["character"]["ref"]]: c for c in dramaturgy["casts"]}
    assert casts["西谷"]["billing"] == "lead"
    # 空で返した値(pace)は消さず、返した値だけ変える
    assert casts["西谷"]["performance"] == {"title": "名コンセルジュ", "description": "落ち着いた低い声", "pace": "ゆっくり"}
    assert (casts["宿の客"]["billing"], casts["宿の客"]["accent"]) == ("minor", "関西弁")
    assert "voice_gender" not in casts["宿の客"]
    # 配役した人物は作品の登場人物に加わる
    assert [names[r["ref"]] for r in dramaturgy["characters"]] == ["西谷", "父", "宿の客"]


def test_audition_sets_actor_voices(client, ctx, fake):
    fake["generator"] = _FakeGenerator(
        _reply(
            AuditionReply,
            auditions=[
                VoiceChoice(character="西谷", voice_id="ja-jp-advisor-1", reason="低い男性の声"),
                VoiceChoice(character="父", voice_id="ja-jp-tutor-1", reason="配役が無い"),
                VoiceChoice(character="西谷", voice_id="kore", reason="一覧に無い(言語が違う)"),
            ],
        )
    )
    resp = _send(client, ctx, "one_shot", step="audition")
    assert resp.status_code == 200, resp.text
    message = parse_yaml(resp)
    assert fake["tasks"] == ["assign_voice"]
    # 声の一覧は作品の言語(ja)で絞り込んで渡す
    request = fake["generator"].calls[0]["messages"][-1].text
    assert "ja-jp-advisor-1" in request and "kore" not in request.split("# 選べる声の一覧")[1]
    assert set(ctx["voice_calls"]) == {"ja"}
    warnings = " ".join(message["warnings"])
    assert "「父」の配役が無い" in warnings and "「kore」は声の一覧に無い" in warnings

    assert _action(client, ctx, message["id"], "apply").status_code == 200
    actors = _dramaturgy(client, ctx)["agents"]["actors"]
    assert len(actors) == 1
    assert (actors[0]["name"], actors[0]["voice_name"], actors[0]["tts_provider"], actors[0]["tts_model"]) == (
        "西谷役の演者",
        "ja-jp-advisor-1",
        "Gemini",
        "gemini-3.8-flash-lite-tts",
    )

    # 2回目は同じ演者の声を変える(演者は増えない)
    fake["generator"] = _FakeGenerator(
        _reply(AuditionReply, auditions=[VoiceChoice(character="西谷", voice_id="ja-jp-tutor-1", reason="")])
    )
    message = parse_yaml(_send(client, ctx, "one_shot", step="audition"))
    assert message["changed_fields"] == ["「西谷」の声をja-jp-tutor-1(Tutor 1)にする"]
    _action(client, ctx, message["id"], "apply")
    actors = _dramaturgy(client, ctx)["agents"]["actors"]
    assert [a["voice_name"] for a in actors] == ["ja-jp-tutor-1"]


def test_audition_needs_dramaturgy_language(client, ctx, fake):
    client.post(f"{ctx['base']}/edit", content=f"dramaturgies: [{{id: {ctx['dramaturgy_id']}, output_language: null}}]")
    fake["generator"] = _FakeGenerator(_reply(AuditionReply, auditions=[]))
    resp = _send(client, ctx, "one_shot", step="audition")
    assert resp.status_code == 400 and "Output Language" in resp.text


def test_voices_are_listed_by_language(client, ctx):
    result = parse_yaml(client.get(f"/projects/{ctx['pid']}/voices", params={"language": "ja"}))
    assert (result["provider"], result["model"]) == ("Gemini", "gemini-3.8-flash-lite-tts")
    assert [v["voice_id"] for v in result["voices"]] == ["ja-jp-advisor-1", "ja-jp-tutor-1"]
    assert result["voices"][0]["accent"] == "Osaka Japanese"


def test_voices_need_tts_setting(client, project):
    resp = client.get(f"/projects/{project.project_id}/voices")
    assert resp.status_code == 400 and "音声合成" in resp.text
