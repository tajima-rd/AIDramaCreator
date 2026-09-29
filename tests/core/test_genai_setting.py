"""
プロジェクトの生成AIの設定(project.yamlのgenaiセクション)と、そこから生成器を作るfactory。

- 設定したLLM/TTSが、project.yamlを経由してそのまま読み戻せること(未設定ならgenaiセクションを書かない)
- 更新日時の更新等、Projectを作り直す操作でも設定が消えないこと
- APIキーをproject.yamlに書かず、~/.aidc/secrets.env(テストではtmp_path)に保存したものだけを使い、
  シェルの環境変数(GEMINI_API_KEY等)は読まないこと
- 以前のproject.yamlにあったapi_key_envは無視して読めること
- 設定・APIキーが無い場合と未対応のクライアントは、ValueErrorになること
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
from core.service.process.genai.generator_builder import (  # noqa: E402
    build_speech_generator,
    build_text_generator,
)


@pytest.fixture
def project(tmp_path):
    return create_project_files(str(tmp_path / "TEST_PROJECT_00"), "TEST_IMPLEMENT__genai")


def _spec(project) -> dict:
    with open(project.layout.project_yaml_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_no_genai_section_when_unset(project):
    assert "genai" not in _spec(project)
    loaded = read_project(project.layout.root_dir)
    assert loaded.llm is None and loaded.tts is None


def test_settings_round_trip(project):
    project.llm = LlmSetting(client="Gemini", model="gemini-3.5-flash")
    project.tts = TtsSetting(client="Gemini", model="gemini-3.1-flash-tts-preview")
    write_project(project)

    # 未設定(None)の項目はproject.yamlに書かない
    assert _spec(project)["genai"] == {
        "llm": {"client": "Gemini", "model": "gemini-3.5-flash"},
        "tts": {"client": "Gemini", "model": "gemini-3.1-flash-tts-preview"},
    }
    loaded = read_project(project.layout.root_dir)
    assert loaded.llm == project.llm
    assert loaded.tts == project.tts

    touch_modified(project.layout)
    assert read_project(project.layout.root_dir).llm == project.llm

    # 手元のサーバー: URLまで(APIキーに関わる項目は無い)
    project.llm = LlmSetting(client="LlamaCpp", model="qwen", api_url="http://localhost:8080")
    write_project(project)
    assert _spec(project)["genai"]["llm"] == {"client": "LlamaCpp", "model": "qwen", "api_url": "http://localhost:8080"}
    assert read_project(project.layout.root_dir).llm == project.llm


def test_legacy_api_key_env_is_ignored(project):
    spec = _spec(project)
    spec["genai"] = {"llm": {"client": "LlamaCpp", "model": "qwen", "api_url": "http://x", "api_key_env": "OLD_KEY"}}
    with open(project.layout.project_yaml_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(spec, f)
    assert read_project(project.layout.root_dir).llm == LlmSetting(client="LlamaCpp", model="qwen", api_url="http://x")


def test_build_generators(project):
    secret_env_store.save_secret("AIDC_GEMINI_API_KEY", "dummy-key")
    project.llm = LlmSetting(client="Gemini", model="gemini-3.5-flash")
    project.tts = TtsSetting(client="Gemini", model="gemini-3.1-flash-tts-preview")
    write_project(project)
    loaded = read_project(project.layout.root_dir)

    llm = build_text_generator(loaded)
    assert isinstance(llm, TextGenerator) and llm.model_name == "gemini-3.5-flash"
    tts = build_speech_generator(loaded)
    assert isinstance(tts, SpeechGenerator) and tts.model_name == "gemini-3.1-flash-tts-preview"
    assert "dummy-key" not in open(project.layout.project_yaml_path, encoding="utf-8").read()


def test_build_errors(project, monkeypatch):
    with pytest.raises(ValueError):
        build_text_generator(project)  # 設定が無い
    project.llm = LlmSetting(client="Unknown", model="x")
    with pytest.raises(ValueError):
        build_text_generator(project)  # 未対応のクライアント
    project.llm = LlmSetting(client="Gemini", model="gemini-3.5-flash")
    monkeypatch.setenv("GEMINI_API_KEY", "from-shell")  # シェルの環境変数は読まない
    monkeypatch.setenv("AIDC_GEMINI_API_KEY", "from-shell")
    with pytest.raises(ValueError, match="AIDC_GEMINI_API_KEY"):
        build_text_generator(project)  # APIキーが無い
