# tests/api/test_dataset.py
"""
Dataset(routers/dataset.py)の結合テスト。

- datasets/に手で置いたCSVも、一覧に出た時点でfile_idが発行され、中身を読めること
- データメタデータYAMLは、無ければ404、自由記述欄の更新で作られ、履歴が追記されること
- 削除すると、データ本体・サイドカーYAML・登録がまとめて消えること
- 知らないfile_idは404
"""

from tests.conftest import parse_yaml


def _place_csv(project, filename="data.csv", csv_text="a,b\n1,2\n"):
    """datasets/にCSVを手で置く(ドラマの定義ができるまで、CSVを保存するAPIは無い)。"""
    datasets_dir = project.layout.datasets_dir
    with open(f"{datasets_dir}/{filename}", "w", encoding="utf-8") as f:
        f.write(csv_text)
    return csv_text


def test_list_get_and_delete_placed_csv(client, project):
    csv_text = _place_csv(project)
    listed = parse_yaml(client.get(f"/projects/{project.project_id}/datasets"))["datasets"]
    assert [(d["filename"], d["file_format"], d["drama_id"]) for d in listed] == [("data.csv", "csv", None)]
    file_id = listed[0]["file_id"]

    resp = client.get(f"/projects/{project.project_id}/datasets/{file_id}")
    assert resp.status_code == 200
    assert parse_yaml(resp)["csv"] == csv_text

    resp = client.delete(f"/projects/{project.project_id}/datasets/{file_id}")
    assert resp.status_code == 200

    resp = client.get(f"/projects/{project.project_id}/datasets")
    assert parse_yaml(resp)["datasets"] == []


def test_update_and_get_dataset_metadata(client, project):
    _place_csv(project)
    file_id = parse_yaml(client.get(f"/projects/{project.project_id}/datasets"))["datasets"][0]["file_id"]
    assert client.get(f"/projects/{project.project_id}/datasets/{file_id}/metadata").status_code == 404

    resp = client.put(
        f"/projects/{project.project_id}/datasets/{file_id}/metadata",
        json={"description": "説明", "tags": ["x"], "message": "first"},
    )
    assert resp.status_code == 200
    metadata = parse_yaml(client.get(f"/projects/{project.project_id}/datasets/{file_id}/metadata"))
    assert metadata["dataset"]["description"] == "説明"
    assert metadata["dataset"]["file_id"] == file_id
    assert metadata["dataset"]["drama_id"] is None
    assert [h["message"] for h in metadata["dataset"]["history"]] == ["first"]


def test_get_unknown_dataset_returns_404(client, project):
    resp = client.get(f"/projects/{project.project_id}/datasets/does-not-exist")
    assert resp.status_code == 404
