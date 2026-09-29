# tests/api/test_project.py
"""Project CRUD(main.py分割後はrouters/project.pyに対応する見込み)のcharacterization test。"""

import yaml

from tests.conftest import parse_yaml


def test_create_and_get_project(client, tmp_path):
    root_dir = tmp_path / "TEST_PROJECT_01"
    resp = client.post("/projects", json={"path": str(root_dir), "name": "TEST_IMPLEMENT__01"})
    assert resp.status_code == 200
    created = parse_yaml(resp)
    assert created["name"] == "TEST_IMPLEMENT__01"

    resp = client.get(f"/projects/{created['project_id']}")
    assert resp.status_code == 200
    assert parse_yaml(resp)["project_id"] == created["project_id"]


def test_create_project_rejects_nonempty_directory(client, tmp_path):
    root_dir = tmp_path / "TEST_PROJECT_02"
    root_dir.mkdir()
    (root_dir / "existing_file.txt").write_text("dummy")

    resp = client.post("/projects", json={"path": str(root_dir), "name": "TEST_IMPLEMENT__02"})
    assert resp.status_code == 400


def test_get_unknown_project_returns_404(client):
    resp = client.get("/projects/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


def test_list_projects_includes_created(client, project):
    resp = client.get("/projects")
    assert resp.status_code == 200
    project_ids = [p["project_id"] for p in parse_yaml(resp)["projects"]]
    assert project.project_id in project_ids


def test_save_as_into_new_directory(client, project, tmp_path):
    dest = tmp_path / "TEST_PROJECT_03"
    resp = client.post(
        f"/projects/{project.project_id}/save-as",
        json={"path": str(dest), "name": "TEST_IMPLEMENT__03"},
    )
    assert resp.status_code == 200
    saved = parse_yaml(resp)
    assert saved["project_id"] != project.project_id
    assert saved["name"] == "TEST_IMPLEMENT__03"
    assert (dest / "project.yaml").is_file()


def test_save_as_into_empty_existing_directory(client, project, tmp_path):
    dest = tmp_path / "TEST_PROJECT_04"
    dest.mkdir()
    resp = client.post(f"/projects/{project.project_id}/save-as", json={"path": str(dest)})
    assert resp.status_code == 200
    saved = parse_yaml(resp)
    assert saved["project_id"] != project.project_id
    assert (dest / "project.yaml").is_file()


def test_save_as_rejects_nonempty_directory_or_file(client, project, tmp_path):
    nonempty = tmp_path / "TEST_PROJECT_05"
    nonempty.mkdir()
    (nonempty / "existing_file.txt").write_text("dummy")
    resp = client.post(f"/projects/{project.project_id}/save-as", json={"path": str(nonempty)})
    assert resp.status_code == 400

    a_file = tmp_path / "TEST_PROJECT_06"
    a_file.write_text("dummy")
    resp = client.post(f"/projects/{project.project_id}/save-as", json={"path": str(a_file)})
    assert resp.status_code == 400


def test_created_project_has_database_and_paths(client, tmp_path):
    root_dir = tmp_path / "TEST_PROJECT_07"
    resp = client.post("/projects", json={"path": str(root_dir), "name": "TEST_IMPLEMENT__07"})
    assert resp.status_code == 200
    assert (root_dir / "project.db").is_file()
    spec = yaml.safe_load((root_dir / "project.yaml").read_text(encoding="utf-8"))
    assert "datasets" not in spec
    assert spec["paths"]["project_db"] == "project.db"
