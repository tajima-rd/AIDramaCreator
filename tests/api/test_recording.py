# tests/api/test_recording.py
"""
音声の生成(Dramaturgy EditorのRecordingタブ。/projects/{id}/recordings)の結合テスト。音声合成は偽物に差し替える(提供元を呼ばない)。

- 作品で作れる言語は、制作の言語(音声にする文)・既定の音声の言語・訳文のある言語(その言語の訳文。言語の一覧の順)
- シーンごとに足りないもの(演出付きの原稿の無い台詞・その言語の文の無い台詞・声の無い配役・台詞の無いシーン)を示し、あれば断る(音声合成を呼ばない)
- 台詞の順に演者の声(読む言語の声があればそれ、無ければ既定の声)で読み、台詞の後の間を挟んでmp3にする。音声合成への指示は
  配役の演じ方・訛り・場所・演出から作り、「TRANSCRIPTだけを読む」と明記する。制作の言語以外で読むときは、制作の言語で書いた設定を渡さない
- 音声は<プロジェクト>/recordings/<作品>/<言語>/<シーン>.mp3に置き、生成し直すと上書きする
"""

import io
import os
import wave

import pytest
import yaml
from pydub import AudioSegment

from core.service.process.production import scene_recorder
from tests.conftest import parse_yaml

WORLD = """
characters:
  - {key: nishitani, name: 西谷}
  - {key: guest, name: 客}
locations:
  - {key: lift, name: 第1リフト}
dramaturgy:
  title: ハチ北
  input_language: ja
  output_language: zh-CN
  characters: [{ref: nishitani}, {ref: guest}]
  locations: [{ref: lift}]
  casts:
    - {key: nishitani_cast, character: {ref: nishitani}, language: ja, accent: Kansai dialect,
       performance: {title: Reliable Guide, pace: Slow}}
    - {key: guest_cast, character: {ref: guest}, language: en}
  agents:
    actors:
      - {name: 西谷役の演者, cast: {ref: nishitani_cast}, voice_name: ja-jp-advisor-1}
      - {name: 客役の演者, cast: {ref: guest_cast}, voice_name: Kore, tts_provider: Gemini, tts_model: other-tts,
         voices: [{language: en, voice_name: en-us-concierge-6}]}
  acts:
    - order: 0
      scenes:
        - order: 0
          title: リフト乗り場
          location: {ref: lift}
          situation: {time_of_day: Morning}
          script:
            lines:
              - {key: l1, order: 0, cast: {ref: nishitani_cast}, text: ようこそ。}
              - {key: l2, order: 1, cast: {ref: guest_cast}, text: どうも。}
          elements:
            - {type: dialogue, order: 0, line: {ref: l1}, cast: {ref: nishitani_cast}, text: "[excited] ようこそ。",
               action: Waves, direction: {style: Warm, emotion: Glad, pause_after: Long},
               translations: [{language: zh-CN, text: "[excited] 欢迎。"}, {language: fr, text: "[excited] Bienvenue."},
                              {language: en, text: "[excited] Welcome."}]}
            - {type: dialogue, order: 1, line: {ref: l2}, cast: {ref: guest_cast}, text: どうも。}
        - order: 1
          title: 未演出
          script:
            lines:
              - {key: l3, order: 0, cast: {ref: guest_cast}, text: "あれ?"}
        - {order: 2, title: 台詞なし}
"""

TONE_MS = 200


def _wav() -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(b"\x00\x00" * (24000 * TONE_MS // 1000))
    return out.getvalue()


class _FakeSpeech:
    def __init__(self, key, calls):
        self.key = key
        self.calls = calls

    def synthesize(self, text, voice):
        self.calls.append({"generator": self.key, "voice": voice, "text": str(text)})
        return _wav()


@pytest.fixture
def speech(monkeypatch):
    calls = []
    monkeypatch.setattr(
        scene_recorder, "build_actor_speech_generator", lambda project, client, model: _FakeSpeech((client, model), calls)
    )
    return calls


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
        "root": project.layout.root_dir,
        "draft_id": created["draft_id"],
        "dramaturgy_id": dramaturgy["id"],
        "scene_ids": [s["id"] for s in scenes],
        "url": f"/projects/{pid}/recordings",
    }


def _list(client, ctx, language=""):
    params = {"draft_id": ctx["draft_id"], "dramaturgy_id": ctx["dramaturgy_id"], "language": language}
    resp = client.get(ctx["url"], params=params)
    assert resp.status_code == 200, resp.text
    return parse_yaml(resp)


def _record(client, ctx, scene_index, language):
    body = {
        "draft_id": ctx["draft_id"],
        "dramaturgy_id": ctx["dramaturgy_id"],
        "scene_id": ctx["scene_ids"][scene_index],
        "language": language,
    }
    return client.post(ctx["url"], content=yaml.safe_dump(body))


def test_list_shows_languages_and_problems(client, ctx):
    result = _list(client, ctx)
    assert [(lang["code"], lang["source"]) for lang in result["languages"]] == [
        ("ja", "text"),
        ("zh-CN", "translation"),
        ("en", "translation"),
        ("fr", "translation"),
    ]
    assert result["language"] == "ja"
    first, second, third = result["scenes"]
    assert (first["act_number"], first["scene_number"], first["problems"], first["recorded"]) == (1, 1, [], False)
    assert "台詞1に演出付きの原稿がありません" in second["problems"][0]
    assert "台詞がありません" in third["problems"][0]
    # 訳文の無い台詞は、音声の言語では足りない
    zh = _list(client, ctx, "zh-CN")["scenes"][0]
    assert zh["problems"] == ["台詞2にzh-CNの訳文がありません。"]
    assert client.get(ctx["url"], params={"draft_id": ctx["draft_id"], "dramaturgy_id": ctx["dramaturgy_id"], "language": "de"}).status_code == 400


def test_record_scene_writes_mp3(client, ctx, speech):
    resp = _record(client, ctx, 0, "ja")
    assert resp.status_code == 200, resp.text
    info = parse_yaml(resp)
    assert info["recorded"] and info["size"] > 0
    # 演者の声で台詞の順に読む。提供元・モデルが空の演者はプロジェクトの設定((None, None)で作る)
    assert [(c["voice"], c["generator"]) for c in speech] == [
        ("ja-jp-advisor-1", (None, None)),
        ("Kore", ("Gemini", "other-tts")),
    ]
    prompt = speech[0]["text"]
    for text in ("AUDIO PROFILE: 西谷", "Reliable Guide", "THE SCENE: 第1リフト / Morning", "Waves", "Style: Warm", "Emotion: Glad",
                 "Pace: Slow", "Accent: Kansai dialect", "Language: 日本語 (ja). Read ONLY the text under TRANSCRIPT",
                 "# TRANSCRIPT\n[excited] ようこそ。"):
        assert text in prompt
    assert "# 1." not in prompt  # 見出しに番号を付けない
    assert "欢迎" not in prompt
    # ファイルの置き場所と、台詞の後の間(Long=1500ms、無ければShort=300ms)
    path = os.path.join(ctx["root"], "recordings", ctx["dramaturgy_id"], "ja", ctx["scene_ids"][0] + ".mp3")
    audio = AudioSegment.from_file(path, format="mp3")
    assert abs(len(audio) - (TONE_MS + 1500 + TONE_MS + 300)) < 150
    # 配信と一覧
    file_resp = client.get(f"{ctx['url']}/{ctx['dramaturgy_id']}/ja/{ctx['scene_ids'][0]}.mp3")
    assert file_resp.status_code == 200 and file_resp.headers["content-type"] == "audio/mpeg"
    assert _list(client, ctx)["scenes"][0]["recorded"] is True
    assert _list(client, ctx, "zh-CN")["scenes"][0]["recorded"] is False


def test_record_translation_reads_that_language(client, ctx, speech):
    draft = f"/projects/{ctx['pid']}/drama-drafts/{ctx['draft_id']}"
    dramaturgy = parse_yaml(client.get(f"{draft}/content"))["dramaturgies"][0]
    scene = next(s for s in dramaturgy["acts"][0]["scenes"] if s["id"] == ctx["scene_ids"][0])
    second = next(e for e in scene["elements"] if e["order"] == 1)
    # 台詞2に英語の訳文を足すと、英語は作れる(フランス語はまだ足りない)
    patch = {"dramaturgies": [{"id": ctx["dramaturgy_id"], "acts": [{"id": dramaturgy["acts"][0]["id"], "scenes": [
        {"id": ctx["scene_ids"][0], "elements": [{"id": second["id"], "translations": [{"language": "en", "text": "Hi."}]}]}]}]}]}
    assert client.post(f"{draft}/edit", content=yaml.safe_dump(patch)).status_code == 200
    assert _list(client, ctx, "fr")["scenes"][0]["problems"] == ["台詞2にfrの訳文がありません。"]
    # 英語の声の無い演者は既定の声で読むことを知らせる(音声は作れる)
    notices = _list(client, ctx, "en")["scenes"][0]["notices"]
    assert notices == ["「西谷」にはenの声が無いので、既定の声(ja-jp-advisor-1)で読みます(CastsタブのVoices by Languageで選べます)。"]
    # 既定の声が英語(配役の言語en)の客は、日本語を既定の声で読む
    assert _list(client, ctx, "ja")["scenes"][0]["notices"] == [
        "「客」にはjaの声が無いので、既定の声(Kore)で読みます(CastsタブのVoices by Languageで選べます)。"
    ]
    resp = _record(client, ctx, 0, "en")
    assert resp.status_code == 200, resp.text
    assert [c["text"].split("# TRANSCRIPT\n")[1] for c in speech] == ["[excited] Welcome.", "Hi."]
    # 英語の声のある演者はそれで、無い演者は既定の声で読む(提供元・モデルは演者の既定)
    assert [(c["voice"], c["generator"]) for c in speech] == [
        ("ja-jp-advisor-1", (None, None)),
        ("en-us-concierge-6", ("Gemini", "other-tts")),
    ]
    # 制作の言語以外では、制作の言語で書いた設定(名前・演じ方・場所・状況・訛り・話す速さ)を渡さない。演出・ト書きは渡す
    prompt = speech[0]["text"]
    for text in ("西谷", "Reliable Guide", "第1リフト", "Morning", "Kansai dialect", "Pace: Slow"):
        assert text not in prompt, text
    for text in ("Waves", "Style: Warm", "Emotion: Glad", "Language: English (en). Read ONLY the text under TRANSCRIPT"):
        assert text in prompt, text
    # 訳文が足りなければ断る
    resp = _record(client, ctx, 0, "fr")
    assert resp.status_code == 400 and "frの訳文がありません" in resp.text and len(speech) == 2


def test_scene_with_problems_is_refused_without_calling_tts(client, ctx, speech):
    for index, text in ((1, "演出付きの原稿がありません"), (2, "台詞がありません")):
        resp = _record(client, ctx, index, "ja")
        assert resp.status_code == 400 and text in resp.text
    assert speech == []
    assert client.get(f"{ctx['url']}/{ctx['dramaturgy_id']}/ja/{ctx['scene_ids'][1]}.mp3").status_code == 404
    # パスを辿る言語は断る
    assert client.get(f"{ctx['url']}/{ctx['dramaturgy_id']}/..%2F/{ctx['scene_ids'][1]}.mp3").status_code in (400, 404)


def test_tts_failure_is_502_and_keeps_previous_file(client, ctx, speech, monkeypatch):
    assert _record(client, ctx, 0, "ja").status_code == 200
    before = _list(client, ctx)["scenes"][0]

    class Broken:
        def synthesize(self, text, voice):
            raise RuntimeError("quota")

    monkeypatch.setattr(scene_recorder, "build_actor_speech_generator", lambda project, client, model: Broken())
    resp = _record(client, ctx, 0, "ja")
    assert resp.status_code == 502 and "quota" in resp.text
    assert _list(client, ctx)["scenes"][0]["recorded_at"] == before["recorded_at"]


def test_language_voices_survive_save_version(client, ctx):
    draft = f"/projects/{ctx['pid']}/drama-drafts/{ctx['draft_id']}"
    actors = parse_yaml(client.get(f"{draft}/content"))["dramaturgies"][0]["agents"]["actors"]
    nishitani = next(a for a in actors if a["voice_name"] == "ja-jp-advisor-1")
    voices = [
        {"language": "en", "voice_name": "en-us-advisor-1", "tts_provider": "Gemini", "tts_model": "gemini-3.8-flash-lite-tts"},
        {"language": "ko", "voice_name": "ko-kr-advisor-1"},
    ]
    patch = {"dramaturgies": [{"id": ctx["dramaturgy_id"], "agents": {"actors": [{"id": nishitani["id"], "voices": voices}]}}]}
    assert client.post(f"{draft}/edit", content=yaml.safe_dump(patch)).status_code == 200
    assert client.post(f"{draft}/confirm", content="note: 声\n").status_code == 200
    model = parse_yaml(client.get(f"/projects/{ctx['pid']}/drama-model"))
    saved = next(a for a in model["dramaturgies"][0]["agents"]["actors"] if a["id"] == nishitani["id"])
    assert saved["voices"] == voices and saved["voice_name"] == "ja-jp-advisor-1"
