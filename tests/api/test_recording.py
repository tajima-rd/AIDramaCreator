# tests/api/test_recording.py
"""
音声の生成(Dramaturgy EditorのRecordingタブ。/projects/{id}/recordings)の結合テスト。音声合成は偽物に差し替える(提供元を呼ばない)。

- 作品で作れる言語は、制作の言語(音声にする文)と、それと違う音声の言語(訳文)
- シーンごとに足りないもの(演出付きの原稿の無い台詞・その言語の文の無い台詞・声の無い配役・台詞の無いシーン)を示し、あれば断る(音声合成を呼ばない)
- 台詞の順に演者の声で読み、台詞の後の間を挟んでmp3にする。音声合成への指示は配役の演じ方・訛り・場所・演出から作る
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
  output_language: zh
  characters: [{ref: nishitani}, {ref: guest}]
  locations: [{ref: lift}]
  casts:
    - {key: nishitani_cast, character: {ref: nishitani}, accent: Kansai dialect, performance: {title: Reliable Guide, pace: Slow}}
    - {key: guest_cast, character: {ref: guest}}
  agents:
    actors:
      - {name: 西谷役の演者, cast: {ref: nishitani_cast}, voice_name: ja-jp-advisor-1}
      - {name: 客役の演者, cast: {ref: guest_cast}, voice_name: Kore, tts_provider: Gemini, tts_model: other-tts}
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
               action: Waves, direction: {style: Warm, emotion: Glad, pause_after: Long}, translated_text: "[excited] 欢迎。"}
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
    assert [(lang["code"], lang["source"]) for lang in result["languages"]] == [("ja", "text"), ("zh", "translated_text")]
    assert result["language"] == "ja"
    first, second, third = result["scenes"]
    assert (first["act_number"], first["scene_number"], first["problems"], first["recorded"]) == (1, 1, [], False)
    assert "台詞1に演出付きの原稿がありません" in second["problems"][0]
    assert "台詞がありません" in third["problems"][0]
    # 訳文の無い台詞は、音声の言語では足りない
    zh = _list(client, ctx, "zh")["scenes"][0]
    assert zh["problems"] == ["台詞2にzhの訳文がありません。"]
    assert client.get(ctx["url"], params={"draft_id": ctx["draft_id"], "dramaturgy_id": ctx["dramaturgy_id"], "language": "en"}).status_code == 400


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
    for text in ("AUDIO PROFILE: 西谷", "Reliable Guide", "THE SCENE: 第1リフト / Morning", "Waves", "Warm", "Emotion: Glad",
                 "Pace: Slow", "Accent: Kansai dialect", "[excited] ようこそ。"):
        assert text in prompt
    assert "欢迎" not in prompt
    # ファイルの置き場所と、台詞の後の間(Long=1500ms、無ければShort=300ms)
    path = os.path.join(ctx["root"], "recordings", ctx["dramaturgy_id"], "ja", ctx["scene_ids"][0] + ".mp3")
    audio = AudioSegment.from_file(path, format="mp3")
    assert abs(len(audio) - (TONE_MS + 1500 + TONE_MS + 300)) < 150
    # 配信と一覧
    file_resp = client.get(f"{ctx['url']}/{ctx['dramaturgy_id']}/ja/{ctx['scene_ids'][0]}.mp3")
    assert file_resp.status_code == 200 and file_resp.headers["content-type"] == "audio/mpeg"
    assert _list(client, ctx)["scenes"][0]["recorded"] is True
    assert _list(client, ctx, "zh")["scenes"][0]["recorded"] is False


def test_record_translation_reads_translated_text(client, ctx, speech):
    patch = {"dramaturgies": [{"id": ctx["dramaturgy_id"], "output_language": "ja"}]}
    # 訳文の無い作品(制作と音声の言語が同じ)では、作れる言語は1つ
    draft = f"/projects/{ctx['pid']}/drama-drafts/{ctx['draft_id']}"
    assert client.post(f"{draft}/edit", content=yaml.safe_dump(patch)).status_code == 200
    assert [lang["code"] for lang in _list(client, ctx)["languages"]] == ["ja"]
    patch = {"dramaturgies": [{"id": ctx["dramaturgy_id"], "output_language": "zh"}]}
    assert client.post(f"{draft}/edit", content=yaml.safe_dump(patch)).status_code == 200
    # 訳文が足りなければ断る
    resp = _record(client, ctx, 0, "zh")
    assert resp.status_code == 400 and "zhの訳文がありません" in resp.text and speech == []


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
