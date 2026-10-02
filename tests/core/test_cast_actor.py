# tests/core/test_cast_actor.py
"""配役の役の重さ(Cast.billing)と、演者の音声合成の提供元・モデル・話者(Actor)の、YAMLとproject.dbの往復。"""

from core.infra.io.model_definition_reader import build_model_definition_from_yaml
from core.infra.io.model_definition_writer import model_definition_to_yaml
from core.model.agent import Actor
from core.model.drama import CastBilling
from core.service.process.edit import drama_draft_editor as editor

MODEL = """
characters: [{key: nishitani, name: 西谷}]
dramaturgy:
  title: ハチ北
  casts:
    - {key: cast_1, character: {ref: nishitani}, billing: lead, voice_gender: male}
  agents:
    actors:
      - {name: 西谷役の演者, cast: {ref: cast_1}, voice_name: ja-jp-advisor-1, tts_provider: Gemini, tts_model: gemini-3.8-flash-lite-tts}
"""


def test_billing_and_actor_tts_are_built():
    dramaturgy = build_model_definition_from_yaml(MODEL).dramaturgy
    assert dramaturgy.casts[0].billing is CastBilling.LEAD
    actor = next(a for a in dramaturgy.agents if isinstance(a, Actor))
    assert (actor.voice_name, actor.tts_provider, actor.tts_model) == (
        "ja-jp-advisor-1",
        "Gemini",
        "gemini-3.8-flash-lite-tts",
    )


def test_billing_and_actor_tts_round_trip_through_project_db(tmp_path):
    db_path = str(tmp_path / "TEST_PROJECT_00" / "project.db")
    expected = model_definition_to_yaml(build_model_definition_from_yaml(MODEL))
    draft = editor.create_draft(db_path, "取り込み")
    editor.import_yaml(db_path, draft.id, expected)
    editor.confirm_draft(db_path, draft.id, "取り込み")
    text = model_definition_to_yaml(editor.load_model(db_path))
    assert text == expected
    assert "billing: lead" in text and "tts_provider: Gemini" in text
