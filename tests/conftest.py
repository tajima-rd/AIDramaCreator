# tests/conftest.py
"""
テスト用の共通fixture。

CLAUDE.md「厳守ルール」に従い、
- ユーザーの実レジストリ(~/.aidc/projects.yaml)とAPIキーの保存先(~/.aidc/secrets.env)は
  絶対に触らない(isolated_registryでtmp_path配下に差し替える)
- 検証用プロジェクトは`TEST_PROJECT_##`の命名規則に沿わせる
"""

import os

import pytest
import yaml
from fastapi.testclient import TestClient

from api.main import app
from core.infra.store import project_registry_store, secret_env_store
from core.service.process.edit.project_editor import create_project_files

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 参考資料(論文のPDF・DOCX)のサンプル。QIDMから持ち込んだRAGのテストが使うが、AIDCには無い
# (第三者の論文をリポジトリに入れないため)。無ければ、それを使うテストはskipする(docs/open_tasks.md)
REFERENCE_SAMPLE_DIR = os.environ.get("AIDC_REFERENCE_SAMPLE_DIR", os.path.join(REPO_ROOT, "tests", "reference_samples"))
requires_reference_samples = pytest.mark.skipif(
    not os.path.isdir(REFERENCE_SAMPLE_DIR), reason="参考資料のサンプル(AIDC_REFERENCE_SAMPLE_DIR)が無い"
)


def parse_yaml(response) -> dict:
    """YAMLレスポンス(api/yaml_io.yaml_response)をdictに戻すテスト用ヘルパー。"""
    return yaml.safe_load(response.text)


@pytest.fixture(autouse=True)
def isolated_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(project_registry_store, "REGISTRY_PATH", str(tmp_path / "registry" / "projects.yaml"))
    # 生成AIのAPIキーの保存先(~/.aidc/secrets.env)にも絶対に触らない
    monkeypatch.setattr(secret_env_store, "SECRETS_PATH", str(tmp_path / "registry" / "secrets.env"))


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def project(tmp_path):
    """TEST_PROJECT_##の命名規則に沿った、テストごとに使い捨てのプロジェクト。"""
    root_dir = tmp_path / "TEST_PROJECT_00"
    project = create_project_files(str(root_dir), "TEST_PROJECT_00")
    project_registry_store.register_project(project.project_id, str(root_dir))
    return project
