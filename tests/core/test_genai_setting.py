"""
プロジェクトの生成AIの設定(project.yamlのgenaiセクション)と、そこから生成器を作るfactory。

- 設定したLLM(作品作り・作業補助)/TTSが、project.yamlを経由してそのまま読み戻せること(未設定ならgenaiセクションを書かない)
- 更新日時の更新等、Projectを作り直す操作でも設定が消えないこと
- APIキーをproject.yamlに書かず、~/.aidc/secrets.env(テストではtmp_path)に保存したものだけを使い、
  シェルの環境変数(GEMINI_API_KEY等)は読まないこと
- 以前のproject.yamlにあったapi_key_envは無視して読めること
- 設定・APIキーが無い場合と未対応のクライアントは、ValueErrorになること
- 文章生成は役割(作品作り・作業補助)で設定を選び、未設定の役割をもう一方で代わりに動かさないこと
- タスク(AgentTask.code)から役割が決まり、システム既定の文章生成のタスクはすべて対応表にあること
"""

import pytest
import yaml

pytest.importorskip("google.genai")

from core.genai import SpeechGenerator, TextGenerator  # noqa: E402
from core.infra.store import secret_env_store  # noqa: E402
from core.infra.store.project_file_store import read_project, write_project  # noqa: E402
from core.project.project import LlmSetting, TtsSetting  # noqa: E402
from core.service.process.edit.project_editor import (  # noqa: E402
    create_project_files,
    touch_modified,
)
from core.infra.io.agent_default_reader import USER_DEFAULT_ROLES, system_default  # noqa: E402
from core.service.process.genai.generator_builder import (  # noqa: E402
    build_speech_generator,
    build_task_text_generator,
    build_text_generator,
)
from core.service.process.genai.llm_role import TASK_LLM_ROLES, LlmRole, llm_role_for_task  # noqa: E402


@pytest.fixture
def project(tmp_path):
    return create_project_files(str(tmp_path / "TEST_PROJECT_00"), "TEST_IMPLEMENT__genai")


def _spec(project) -> dict:
    with open(project.layout.project_yaml_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_no_genai_section_when_unset(project):
    assert "genai" not in _spec(project)
    loaded = read_project(project.layout.root_dir)
    assert loaded.creative_llm is None and loaded.assistive_llm is None and loaded.tts is None


def test_settings_round_trip(project):
    project.creative_llm = LlmSetting(client="Gemini", model="gemini-3.5-flash")
    project.tts = TtsSetting(client="Gemini", model="gemini-3.1-flash-tts-preview")
    write_project(project)

    # 未設定(None)の項目はproject.yamlに書かない
    assert _spec(project)["genai"] == {
        "creative_llm": {"client": "Gemini", "model": "gemini-3.5-flash"},
        "tts": {"client": "Gemini", "model": "gemini-3.1-flash-tts-preview"},
    }
    loaded = read_project(project.layout.root_dir)
    assert loaded.creative_llm == project.creative_llm
    assert loaded.assistive_llm is None
    assert loaded.tts == project.tts

    touch_modified(project.layout)
    assert read_project(project.layout.root_dir).creative_llm == project.creative_llm

    # 手元のサーバー: URLまで(APIキーに関わる項目は無い)
    project.assistive_llm = LlmSetting(client="LlamaCpp", model="qwen", api_url="http://localhost:8080")
    write_project(project)
    assert _spec(project)["genai"]["assistive_llm"] == {
        "client": "LlamaCpp",
        "model": "qwen",
        "api_url": "http://localhost:8080",
    }
    loaded = read_project(project.layout.root_dir)
    assert loaded.assistive_llm == project.assistive_llm
    assert loaded.creative_llm == project.creative_llm


def test_legacy_api_key_env_is_ignored(project):
    spec = _spec(project)
    spec["genai"] = {
        "creative_llm": {
            "client": "LlamaCpp",
            "model": "qwen",
            "api_url": "http://x",
            "api_key_env": "OLD_KEY",
        }
    }
    with open(project.layout.project_yaml_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(spec, f)
    assert read_project(project.layout.root_dir).creative_llm == LlmSetting(
        client="LlamaCpp", model="qwen", api_url="http://x"
    )


def test_build_generators(project):
    secret_env_store.save_secret("AIDC_GEMINI_API_KEY", "dummy-key")
    project.creative_llm = LlmSetting(client="Gemini", model="gemini-3.5-flash")
    project.assistive_llm = LlmSetting(client="Gemini", model="gemma-4-31b-it")
    project.tts = TtsSetting(client="Gemini", model="gemini-3.1-flash-tts-preview")
    write_project(project)
    loaded = read_project(project.layout.root_dir)

    llm = build_text_generator(loaded, LlmRole.CREATIVE)
    assert isinstance(llm, TextGenerator) and llm.model_name == "gemini-3.5-flash"
    assert build_text_generator(loaded, LlmRole.ASSISTIVE).model_name == "gemma-4-31b-it"
    tts = build_speech_generator(loaded)
    assert isinstance(tts, SpeechGenerator) and tts.model_name == "gemini-3.1-flash-tts-preview"
    assert "dummy-key" not in open(project.layout.project_yaml_path, encoding="utf-8").read()


def test_build_errors(project, monkeypatch):
    with pytest.raises(ValueError):
        build_text_generator(project, LlmRole.CREATIVE)  # 設定が無い
    project.creative_llm = LlmSetting(client="Unknown", model="x")
    with pytest.raises(ValueError):
        build_text_generator(project, LlmRole.CREATIVE)  # 未対応のクライアント
    project.creative_llm = LlmSetting(client="Gemini", model="gemini-3.5-flash")
    monkeypatch.setenv("GEMINI_API_KEY", "from-shell")  # シェルの環境変数は読まない
    monkeypatch.setenv("AIDC_GEMINI_API_KEY", "from-shell")
    with pytest.raises(ValueError, match="AIDC_GEMINI_API_KEY"):
        build_text_generator(project, LlmRole.CREATIVE)  # APIキーが無い


def test_assistive_does_not_fall_back_to_creative(project):
    secret_env_store.save_secret("AIDC_GEMINI_API_KEY", "dummy-key")
    project.creative_llm = LlmSetting(client="Gemini", model="gemini-3.5-flash")
    # 作業補助が未設定なら、作品作り(課金あり)で代わりに動かさず、設定を促す
    with pytest.raises(ValueError, match="作業補助"):
        build_text_generator(project, LlmRole.ASSISTIVE)


def test_task_llm_roles(project, monkeypatch):
    assert llm_role_for_task("write_dialogue") is LlmRole.CREATIVE
    with pytest.raises(ValueError, match="unknown_task"):
        llm_role_for_task("unknown_task")  # 表に無いタスクは黙って動かさない

    # システム既定の文章生成のタスク(音声合成のActor以外)は、すべて対応表にある
    codes = {task.code for role_name in USER_DEFAULT_ROLES for task in system_default(role_name).tasks}
    assert codes and codes <= set(TASK_LLM_ROLES)

    # タスクから作ると、対応表の役割の設定を使う
    secret_env_store.save_secret("AIDC_GEMINI_API_KEY", "dummy-key")
    project.creative_llm = LlmSetting(client="Gemini", model="gemini-3.5-flash")
    project.assistive_llm = LlmSetting(client="Gemini", model="gemma-4-31b-it")
    monkeypatch.setitem(TASK_LLM_ROLES, "sketch_test", LlmRole.ASSISTIVE)
    assert build_task_text_generator(project, "sketch_test").model_name == "gemma-4-31b-it"
    assert build_task_text_generator(project, "write_dialogue").model_name == "gemini-3.5-flash"
