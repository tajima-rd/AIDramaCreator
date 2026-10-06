# tests/api/test_scene_translation.py
"""
シーンの台詞の翻訳(POST /projects/{id}/drama-drafts/{draft_id}/scene-translation。ScenesタブのTranslation)の結合テスト。
生成AIは偽物に差し替える(提供元を呼ばない)。

- 訳すのは原稿の音声にする文(感情タグ入り。原稿が無ければ台詞)。訳文を返すだけで、下書きは変えない
- 一覧に無い感情タグは外し、訳の無い台詞・無い番号は注意にする。訳さない作品・台詞の無いシーンは断る
- 担当はStageManager(タスクtranslate)
あわせて、ScenesタブのScriptの保存(台詞と、その行の原稿を1回の直接編集で消す)と、台詞と食い違う原稿をRecordingが断ることを確かめる。
"""

import copy

import pytest
import yaml

from core.prompt.scene_translation import LineTranslation, SceneTranslationReply
from core.service.process.genai import scene_translator
from tests.api.test_ai_build import _FakeGenerator
from tests.conftest import parse_yaml

WORLD = """
characters:
  - {key: nishitani, name: 西谷, speech_style: {first_person: わし}}
  - {key: guest, name: 客}
dramaturgy:
  title: ハチ北
  input_language: ja
  output_language: zh-CN
  characters: [{ref: nishitani}, {ref: guest}]
  casts:
    - {key: nishitani_cast, character: {ref: nishitani}}
    - {key: guest_cast, character: {ref: guest}}
  agents:
    stage_managers:
      - {name: 舞台監督, role: 進行を管理する}
    actors:
      - {name: 西谷役, cast: {ref: nishitani_cast}, voice_name: v1}
      - {name: 客役, cast: {ref: guest_cast}, voice_name: v2}
  acts:
    - order: 0
      scenes:
        - order: 0
          title: リフト乗り場
          script:
            lines:
              - {key: l1, order: 0, cast: {ref: nishitani_cast}, text: ようこそ。}
              - {key: l2, order: 1, cast: {ref: guest_cast}, text: どうも。}
              - {key: l3, order: 2, cast: {ref: nishitani_cast}, text: 行こか。}
          elements:
            - {type: dialogue, order: 0, line: {ref: l1}, cast: {ref: nishitani_cast}, text: "[excited] ようこそ。"}
            - {type: dialogue, order: 2, line: {ref: l3}, cast: {ref: nishitani_cast}, text: 行こか。,
               translations: [{language: zh-CN, text: 走吧。}]}
        - {order: 1, title: 台詞なし}
"""


@pytest.fixture
def fake(monkeypatch):
    state = {"tasks": [], "generator": None}

    def build(project, task_code, config=None):
        state["tasks"].append(task_code)
        return state["generator"]

    monkeypatch.setattr(scene_translator, "build_task_text_generator", build)
    return state


@pytest.fixture
def ctx(client, project):
    pid = project.project_id
    created = parse_yaml(client.post(f"/projects/{pid}/drama-drafts", content="title: Dramaturgy Editor\n"))
    base = f"/projects/{pid}/drama-drafts/{created['draft_id']}"
    resp = client.post(f"{base}/import", content=WORLD)
    assert resp.status_code == 200, resp.text
    dramaturgy = parse_yaml(client.get(f"{base}/content"))["dramaturgies"][0]
    scenes = sorted(dramaturgy["acts"][0]["scenes"], key=lambda s: s["order"])
    return {"pid": pid, "base": base, "draft_id": created["draft_id"], "dramaturgy_id": dramaturgy["id"], "scene_ids": [s["id"] for s in scenes]}


def _translate(client, ctx, scene_index=0, language="ko"):
    body = {"dramaturgy_id": ctx["dramaturgy_id"], "scene_id": ctx["scene_ids"][scene_index], "language": language}
    return client.post(f"{ctx['base']}/scene-translation", content=yaml.safe_dump(body))


def _scene(client, ctx):
    dramaturgy = parse_yaml(client.get(f"{ctx['base']}/content"))["dramaturgies"][0]
    return next(s for s in dramaturgy["acts"][0]["scenes"] if s["id"] == ctx["scene_ids"][0])


def test_translate_returns_translations_without_changing_draft(client, ctx, fake):
    before = _scene(client, ctx)
    fake["generator"] = _FakeGenerator(
        SceneTranslationReply(
            translations=[
                LineTranslation(number=1, translated_text="[excited] 欢迎。[angry]"),
                LineTranslation(number=3, translated_text="走吧。"),
                LineTranslation(number=7, translated_text="無い"),
            ],
            warnings=["地名の読みを確かめてください"],
        )
    )
    resp = _translate(client, ctx)
    assert resp.status_code == 200, resp.text
    result = parse_yaml(resp)
    assert fake["tasks"] == ["translate"]
    # 既定の音声の言語(zh-CN)でなくても、選んだ言語へ訳す
    assert result["language"] == "ko"
    assert [(line["number"], line["translated_text"]) for line in result["lines"]] == [
        (1, "[excited] 欢迎。"),
        (2, ""),
        (3, "走吧。"),
    ]
    warnings = " ".join(result["warnings"])
    for text in ("地名の読み", "「[angry]」は使えない", "台詞7はありません", "台詞2の訳がありません"):
        assert text in warnings
    # 訳すのは原稿の音声にする文(感情タグ入り)、原稿が無ければ台詞。担当は作品のStageManager
    call = fake["generator"].calls[0]
    request = call["messages"][-1].text
    for text in ("日本語・日本語(ja) → 韓国語・한국어(ko)", "1. 西谷: [excited] ようこそ。", "2. 客: どうも。", "わし"):
        assert text in request
    assert "舞台監督" in call["system"] and "翻訳する" in call["system"] and "[whispers]" in call["system"]
    assert _scene(client, ctx) == before


def test_translate_is_refused_for_same_language_or_empty_scene(client, ctx, fake):
    fake["generator"] = _FakeGenerator(SceneTranslationReply(translations=[], warnings=[]))
    resp = _translate(client, ctx, 1)
    assert resp.status_code == 400 and "台詞がありません" in resp.text
    # 制作の言語へは訳さない
    resp = _translate(client, ctx, language="ja")
    assert resp.status_code == 400 and "制作の言語です" in resp.text
    assert fake["generator"].calls == []


def test_script_edit_deletes_line_with_its_element_and_recording_flags_mismatch(client, ctx):
    scene = _scene(client, ctx)
    act_id = parse_yaml(client.get(f"{ctx['base']}/content"))["dramaturgies"][0]["acts"][0]["id"]
    ordered = sorted(scene["script"]["lines"], key=lambda line: line["order"])
    elements = {e["line"]["ref"]: e for e in scene["elements"]}
    # ScenesタブのScriptの保存と同じ形: 台詞3を消し(その原稿も消す)、台詞1の文言を変える
    patch = {
        "dramaturgies": [
            {
                "id": ctx["dramaturgy_id"],
                "acts": [
                    {
                        "id": act_id,
                        "scenes": [
                            {
                                "id": ctx["scene_ids"][0],
                                "script": {
                                    "lines": [
                                        {"id": ordered[0]["id"], "order": 0, "text": "ようこそ、ハチ北へ。"},
                                        {"id": ordered[2]["id"], "delete": True},
                                    ]
                                },
                                "elements": [{"id": elements[ordered[2]["key"]]["id"], "delete": True}],
                            }
                        ],
                    }
                ],
            }
        ]
    }
    resp = client.post(f"{ctx['base']}/edit", content=yaml.safe_dump(patch, allow_unicode=True))
    assert resp.status_code == 200, resp.text
    after = _scene(client, ctx)
    assert len(after["script"]["lines"]) == 2 and len(after["elements"]) == 1
    # 原稿が今の台詞と食い違う行・原稿の無い行があれば、Recordingは作らない
    params = {"draft_id": ctx["draft_id"], "dramaturgy_id": ctx["dramaturgy_id"], "language": "ja"}
    problems = parse_yaml(client.get(f"/projects/{ctx['pid']}/recordings", params=params))["scenes"][0]["problems"]
    assert any("台詞1の原稿が、今の台詞と食い違います" in p for p in problems)
    assert any("台詞2に演出付きの原稿がありません" in p for p in problems)



def test_translation_uses_current_line_when_direction_is_stale(client, ctx, fake):
    scene = _scene(client, ctx)
    act_id = parse_yaml(client.get(f"{ctx['base']}/content"))["dramaturgies"][0]["acts"][0]["id"]
    first = sorted(scene["script"]["lines"], key=lambda line: line["order"])[0]
    patch = {"dramaturgies": [{"id": ctx["dramaturgy_id"], "acts": [{"id": act_id, "scenes": [
        {"id": ctx["scene_ids"][0], "script": {"lines": [{"id": first["id"], "text": "ようこそ、ハチ北へ。"}]}}]}]}]}
    assert client.post(f"{ctx['base']}/edit", content=yaml.safe_dump(patch, allow_unicode=True)).status_code == 200
    fake["generator"] = _FakeGenerator(SceneTranslationReply(translations=[], warnings=[]))
    assert _translate(client, ctx).status_code == 200
    request = fake["generator"].calls[0]["messages"][-1].text
    assert "1. 西谷: ようこそ、ハチ北へ。" in request and "[excited]" not in request.split("# 訳す台詞")[1]


def test_many_translations_survive_save_version(client, ctx):
    scene = _scene(client, ctx)
    act_id = parse_yaml(client.get(f"{ctx['base']}/content"))["dramaturgies"][0]["acts"][0]["id"]
    element = next(e for e in scene["elements"] if e["order"] == 2)
    translations = [
        {"language": lang, "text": text}
        for lang, text in (("zh-CN", "走吧。"), ("en", "Let's go."), ("ko", "가자."), ("fr", "Allons-y."), ("es", "Vamos."))
    ]
    patch = {"dramaturgies": [{"id": ctx["dramaturgy_id"], "acts": [{"id": act_id, "scenes": [
        {"id": ctx["scene_ids"][0], "elements": [{"id": element["id"], "translations": translations}]}]}]}]}
    # 同じ言語が2つある訳文は断る
    duplicated = copy.deepcopy(patch)
    duplicated["dramaturgies"][0]["acts"][0]["scenes"][0]["elements"][0]["translations"] = translations + [{"language": "en", "text": "Go."}]
    resp = client.post(f"{ctx['base']}/edit", content=yaml.safe_dump(duplicated, allow_unicode=True))
    assert resp.status_code == 400 and "en が2つあります" in resp.text
    assert client.post(f"{ctx['base']}/edit", content=yaml.safe_dump(patch, allow_unicode=True)).status_code == 200
    assert client.post(f"{ctx['base']}/confirm", content="note: 訳文\n").status_code == 200
    # 正本(project.dbの訳文の表)から読み直しても、5言語の訳文が並びのまま残る
    model = parse_yaml(client.get(f"/projects/{ctx['pid']}/drama-model"))
    saved = next(
        e
        for s in model["dramaturgies"][0]["acts"][0]["scenes"]
        for e in s.get("elements") or []
        if e["id"] == element["id"]
    )
    assert saved["translations"] == translations
