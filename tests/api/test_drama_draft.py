# tests/api/test_drama_draft.py
"""
作品モデルの正本・版・下書き(routers/drama_model.py・drama_draft.py)の結合テスト。

- 下書きを作り、取り込み・Apply(部分YAML)・Undoをして、確定すると正本と版ができること
- 正本は確定まで変わらないこと
- 古い版を元にした確定は409、形・参照の誤りは400、知らない下書き・版は404
"""

from pathlib import Path

from tests.conftest import REPO_ROOT, parse_yaml
from tests.core.test_drama_draft_editor import PROJECT_MODEL

SAMPLE_DRAMA_DIR = Path(REPO_ROOT) / "apps" / "sample_data" / "令和但馬道中膝栗毛" / "drama"


def _create(client, project, title="下書き"):
    resp = client.post(f"/projects/{project.project_id}/drama-drafts", content=f"title: {title}\n")
    assert resp.status_code == 200
    return parse_yaml(resp)


def _drafts(project, draft_id, action=""):
    return f"/projects/{project.project_id}/drama-drafts/{draft_id}{action}"


def test_draft_lifecycle_creates_version_and_canonical_model(client, project):
    draft = _create(client, project)
    assert (draft["status"], draft["base_version"]) == ("open", None)

    resp = client.post(_drafts(project, draft["draft_id"], "/import"), content=PROJECT_MODEL)
    assert parse_yaml(resp) == {"revision": 1}
    content = parse_yaml(client.get(_drafts(project, draft["draft_id"], "/content")))
    assert [d["title"] for d in content["dramaturgies"]] == ["港町の灯", "港町の灯(続編)"]

    # 部分YAMLのApply: 2つ目の作品の題だけを変える
    second_id = content["dramaturgies"][1]["id"]
    patch = f"dramaturgies: [{{id: {second_id}, title: 提案された題}}]"
    assert parse_yaml(
        client.post(_drafts(project, draft["draft_id"], "/apply"), content=patch)
    ) == {"revision": 2}
    content = parse_yaml(client.get(_drafts(project, draft["draft_id"], "/content")))
    assert content["dramaturgies"][1]["title"] == "提案された題"

    # 確定までは正本は空
    model = parse_yaml(client.get(f"/projects/{project.project_id}/drama-model"))
    assert "dramaturgies" not in model

    resp = client.post(_drafts(project, draft["draft_id"], "/confirm"), content="note: 最初の版\n")
    assert parse_yaml(resp) == {"version": 1}
    model = parse_yaml(client.get(f"/projects/{project.project_id}/drama-model"))
    assert [d["title"] for d in model["dramaturgies"]] == ["港町の灯", "提案された題"]
    # 値の無い属性は書かない(モデル定義YAMLの形)
    assert "latitude" not in model["locations"][1]

    versions = parse_yaml(client.get(f"/projects/{project.project_id}/drama-model/versions"))
    assert versions["current_version"] == 1
    assert [(v["version"], v["note"]) for v in versions["versions"]] == [(1, "最初の版")]
    snapshot = parse_yaml(client.get(f"/projects/{project.project_id}/drama-model/versions/1"))
    assert snapshot == model

    assert parse_yaml(client.get(_drafts(project, draft["draft_id"])))["status"] == "confirmed"


def test_undo_and_revisions(client, project):
    draft_id = _create(client, project)["draft_id"]
    client.post(_drafts(project, draft_id, "/import"), content=PROJECT_MODEL)
    client.post(_drafts(project, draft_id, "/edit"), content="locations: [{name: 駅}]")
    assert parse_yaml(client.post(_drafts(project, draft_id, "/undo"))) == {"revision": 3}
    names = [
        p["name"]
        for p in parse_yaml(client.get(_drafts(project, draft_id, "/content")))["locations"]
    ]
    assert "駅" not in names
    revisions = parse_yaml(client.get(_drafts(project, draft_id, "/revisions")))["revisions"]
    assert [r["operation"] for r in revisions] == ["create", "import", "edit", "undo"]
    # 履歴の行の中身も読める
    old = parse_yaml(client.get(_drafts(project, draft_id, "/content?revision=2")))
    assert "駅" in [p["name"] for p in old["locations"]]


def test_import_path_and_replace(client, project):
    draft_id = _create(client, project)["draft_id"]
    resp = client.post(
        _drafts(project, draft_id, "/import-path"), content=f"path: {SAMPLE_DRAMA_DIR}\n"
    )
    assert resp.status_code == 200
    content = parse_yaml(client.get(_drafts(project, draft_id, "/content")))
    assert content["dramaturgies"][0]["title"] == "令和但馬道中膝栗毛〜ハチ北スキー場編〜"

    client.post(
        _drafts(project, draft_id, "/import?replace=true"), content="dramaturgy: {title: 別}"
    )
    content = parse_yaml(client.get(_drafts(project, draft_id, "/content")))
    assert [d["title"] for d in content["dramaturgies"]] == ["別"]

    resp = client.post(_drafts(project, draft_id, "/import-path"), content="path: /no/such/model\n")
    assert resp.status_code == 404


def test_stale_draft_confirm_is_conflict(client, project):
    first = _create(client, project, "1つ目")["draft_id"]
    second = _create(client, project, "2つ目")["draft_id"]
    client.post(_drafts(project, first, "/confirm"), content="{}")
    resp = client.post(_drafts(project, second, "/confirm"), content="{}")
    assert resp.status_code == 409


def test_invalid_patch_is_bad_request(client, project):
    draft_id = _create(client, project)["draft_id"]
    bad_ref = "dramaturgy: {title: 題, casts: [{character: {ref: nobody}}]}"
    assert client.post(_drafts(project, draft_id, "/edit"), content=bad_ref).status_code == 400
    assert client.post(_drafts(project, draft_id, "/edit"), content="a: [").status_code == 400
    assert client.post(_drafts(project, draft_id, "/undo")).status_code == 400
    client.post(_drafts(project, draft_id, "/discard"))
    resp = client.post(_drafts(project, draft_id, "/edit"), content="locations: [{name: 駅}]")
    assert resp.status_code == 400


def test_unknown_draft_and_version_are_not_found(client, project):
    assert client.get(_drafts(project, "no-such-draft")).status_code == 404
    assert client.post(_drafts(project, "no-such-draft", "/undo")).status_code == 404
    resp = client.get(f"/projects/{project.project_id}/drama-model/versions/9")
    assert resp.status_code == 404
    assert client.get("/projects/no-such-project/drama-model").status_code == 404


def test_list_drafts_by_status(client, project):
    kept = _create(client, project, "残す")["draft_id"]
    dropped = _create(client, project, "捨てる")["draft_id"]
    client.post(_drafts(project, dropped, "/discard"))
    listed = parse_yaml(client.get(f"/projects/{project.project_id}/drama-drafts?status=open"))
    assert [d["draft_id"] for d in listed["drafts"]] == [kept]
    listed = parse_yaml(client.get(f"/projects/{project.project_id}/drama-drafts"))
    assert len(listed["drafts"]) == 2
