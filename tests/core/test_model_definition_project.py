# tests/core/test_model_definition_project.py
"""モデル定義YAMLから現行の制作の流れを動かす仲介(_model_definition_project)。生成AIは呼ばない。tmp_pathの中だけで動く。"""

import shutil
from pathlib import Path

import pytest

from core.prompt.drama_production import generate_dialogue_prompt, generate_sound_drama_prompt
from core.service.process.production._model_definition_project import (
    ModelDefinitionProject,
    is_model_definition_project,
)

SAMPLE_DATA = Path(__file__).resolve().parents[2] / "apps" / "sample_data"


@pytest.fixture
def project(tmp_path) -> ModelDefinitionProject:
    shutil.copytree(SAMPLE_DATA, tmp_path / "model")
    return ModelDefinitionProject(str(tmp_path))


def test_units_follow_scenes(project, tmp_path):
    assert is_model_definition_project(str(tmp_path))
    units = project.units()
    assert [(u.act_key, u.scene_key, u.number) for u in units] == [
        ("act1", f"plot_{i:03d}", i - 1) for i in range(1, 6)
    ]
    assert units[0].scene.synopsis.startswith("無事に宿で合流を果たした二人は")


def test_dialogue_profiles_are_built_from_characters(project):
    profiles = dict(project.dialogue_profiles())

    assert list(profiles) == ["加藤 喜一", "水野 弥千代"]  # 配役のある人物(話者)だけ
    kiichi = profiles["加藤 喜一"]
    for expected in (
        "# 加藤 喜一（かとう きいち）",
        "* 年齢: 27歳",
        "## 職業とキャリア",
        "* **現在の職業**: システムエンジニア",
        "【喜一の小学校時代】",
        "父親：加藤 誠一（かとう せいいち）",
    ):
        assert expected in kiichi
    prompt = generate_dialogue_prompt(
        project.units()[0].scene.synopsis, project.dialogue_profiles()
    )
    assert "[水野 弥千代]" in prompt


def test_record_script_writes_back_and_reloads(project, tmp_path):
    unit = project.units()[1]
    path = project.record_script(
        unit, [("水野 弥千代", "キタさん、滑るよ！"), ("加藤 喜一", "問題ない。")]
    )

    assert path == tmp_path / "model" / "scripts" / "act_000_scene_001.yaml"
    lines = project.units()[1].scene.script.lines
    assert [(line.cast.character.name, line.text) for line in lines] == [
        ("水野 弥千代", "キタさん、滑るよ！"),
        ("加藤 喜一", "問題ない。"),
    ]
    with pytest.raises(ValueError, match="配役"):
        project.record_script(unit, [("佐々木 翼", "話者ではない")])


def test_scene_yaml_becomes_legacy_scene_for_sound(project):
    scene = project.load_scenes_yaml(
        {
            "scene_id": "scene_000",
            "title": "Inn",
            "transcripts": [
                {
                    "actor_name": "加藤 喜一",
                    "context": "Outside the inn",
                    "scene": "Arms folded",
                    "directors_note": {"style": "Calm", "pace": "Moderate"},
                    "text": "[sighs] 夕食が楽しみだ…",
                    "order": 1,
                }
            ],
        }
    )
    transcript = scene.transcript[0]
    assert transcript.actor.voice_name == "Charon"
    prompt = generate_sound_drama_prompt(transcript)
    assert "AUDIO PROFILE: 加藤 喜一" in prompt and '""' not in prompt  # 性格の見出しは省かれる
    with pytest.raises(ValueError, match="配役"):
        project.load_scenes_yaml(
            {"scene_id": "s", "title": "t", "transcripts": [{"actor_name": "佐々木 翼"}]}
        )


def test_speaker_names_match_without_spaces(project):
    # 生成AIはフルネームの空白を詰めて書くことがある
    project.record_script(project.units()[0], [("加藤喜一", "夕食が楽しみだ…")])
    assert project.units()[0].scene.script.lines[0].cast.character.name == "加藤 喜一"
