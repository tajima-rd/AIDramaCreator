# tests/api/test_geodata_import.py
"""
場所の地図(KML・GeoPackage)の取り込み(POST /projects/{id}/drama-drafts/{draft_id}/import-geodata)の結合テスト。
サンプルはapps/sample_data/ハチ北スキー場ガイド/ハチ北スキー場.kml(Location 11・SiteFlow 7・補助情報5層)。

- 場所・移動は作品の参照になり、補助情報は作品に割り当てたDataset(GeoPackage)になること
- 取り込み直すと、場所はid、移動はoriginとdestinationで同じものを更新すること(増えない)
- 線の端点が場所の面に入らなければ、取り込み全体を断ること(下書きは変わらない)
- project.db(GeoPackage)そのものも取り込めること
"""

import base64
from pathlib import Path

import yaml

from tests.conftest import REPO_ROOT, parse_yaml

SAMPLE_KML = Path(REPO_ROOT) / "apps" / "sample_data" / "ハチ北スキー場ガイド" / "ハチ北スキー場.kml"
GUIDE_ID = "77651a9d-274b-548d-b9a8-b8fa83bae620"
SEQUEL_ID = "0b6a3b1e-5f3c-4d43-9a39-3f0f6b1a2c10"
MODEL = f"""
dramaturgies:
  - id: {GUIDE_ID}
    title: ハチ北スキー場ガイド
  - id: {SEQUEL_ID}
    title: 続編
"""


def _url(project, path=""):
    return f"/projects/{project.project_id}{path}"


def _draft(client, project) -> str:
    draft_id = parse_yaml(client.post(_url(project, "/drama-drafts"), content="title: 取り込み\n"))["draft_id"]
    assert client.post(_url(project, f"/drama-drafts/{draft_id}/import"), content=MODEL).status_code == 200
    return draft_id


def _import(client, project, draft_id, data: bytes, filename="ハチ北スキー場.kml", dramaturgy_id=GUIDE_ID):
    body = yaml.safe_dump(
        {
            "dramaturgy_id": dramaturgy_id,
            "filename": filename,
            "content_base64": base64.b64encode(data).decode("ascii"),
        }
    )
    return client.post(_url(project, f"/drama-drafts/{draft_id}/import-geodata"), content=body)


def _content(client, project, draft_id) -> dict:
    return parse_yaml(client.get(_url(project, f"/drama-drafts/{draft_id}/content")))


def _flows(content: dict, dramaturgy_id: str = GUIDE_ID) -> list[tuple[str, str]]:
    names = {loc["key"]: loc["name"] for loc in content["locations"]}
    flows = {flow["key"]: flow for flow in content["site_flows"]}
    dramaturgy = next(d for d in content["dramaturgies"] if d["id"] == dramaturgy_id)
    return [
        (names[flows[r["ref"]]["origin"]["ref"]], names[flows[r["ref"]]["destination"]["ref"]])
        for r in dramaturgy["site_flows"]
    ]


def test_import_kml_into_dramaturgy(client, project):
    draft_id = _draft(client, project)
    resp = _import(client, project, draft_id, SAMPLE_KML.read_bytes())
    assert resp.status_code == 200, resp.text
    result = parse_yaml(resp)
    assert (result["locations_created"], result["locations_updated"]) == (11, 0)
    assert (result["site_flows_created"], result["site_flows_updated"]) == (7, 0)
    assert result["auxiliary_layers"] == {"リフト乗降場所": 20, "リフト": 13, "施設": 22, "チケット売り場": 2, "参照": 2}

    content = _content(client, project, draft_id)
    guide = next(d for d in content["dramaturgies"] if d["id"] == GUIDE_ID)
    assert len(guide["locations"]) == 11
    # KMLに書いたidを保つ
    kids = next(loc for loc in content["locations"] if loc["name"] == "キッズパーク")
    assert kids["id"] == "41cbd4c2-3d8f-5551-b58c-554c79fa2990"
    assert kids["geometry"].startswith("POLYGON ((134.551956 35.406942")
    assert _flows(content)[:2] == [("最初の場所", "間違いポイント"), ("間違いポイント", "ちょっと急なエリア")]
    # 別の作品は場所を参照しない
    sequel = next(d for d in content["dramaturgies"] if d["id"] == SEQUEL_ID)
    assert "locations" not in sequel

    # 補助情報は、作品に割り当てたDataset(GeoPackage)になる
    datasets = parse_yaml(client.get(_url(project, "/datasets")))["datasets"]
    auxiliary = next(d for d in datasets if d["file_id"] == result["auxiliary_file_id"])
    assert auxiliary["filename"] == "ハチ北スキー場_補助情報.gpkg" == result["auxiliary_filename"]
    assert (auxiliary["drama_id"], auxiliary["file_format"]) == (GUIDE_ID, "gpkg")


def test_reimport_updates_instead_of_adding(client, project):
    draft_id = _draft(client, project)
    data = SAMPLE_KML.read_bytes()
    first = parse_yaml(_import(client, project, draft_id, data))
    edited = data.replace("二番目の難関。".encode(), "二番目の難関。ゆっくり滑ろう。".encode())
    result = parse_yaml(_import(client, project, draft_id, edited))
    assert (result["locations_created"], result["locations_updated"]) == (0, 11)
    assert (result["site_flows_created"], result["site_flows_updated"]) == (0, 7)
    # 補助情報のDatasetは同じものを上書きする
    assert result["auxiliary_file_id"] == first["auxiliary_file_id"]

    content = _content(client, project, draft_id)
    assert len(content["locations"]) == 11 and len(content["site_flows"]) == 7
    slope = next(loc for loc in content["locations"] if loc["name"] == "少し急")
    assert slope["instruction"] == "二番目の難関。ゆっくり滑ろう。"


def test_site_flow_endpoint_outside_locations_is_rejected(client, project):
    draft_id = _draft(client, project)
    before = parse_yaml(client.get(_url(project, f"/drama-drafts/{draft_id}/revisions")))["revisions"]
    # ライン 1の始点(最初の場所の中)を、どの場所にも入らない位置に動かす
    data = SAMPLE_KML.read_bytes().replace(b"134.5579457,35.4046866", b"134.5,35.3")
    resp = _import(client, project, draft_id, data)
    assert resp.status_code == 400
    assert "ライン 1" in resp.text and "どのLocationの面にも入っていません" in resp.text
    after = parse_yaml(client.get(_url(project, f"/drama-drafts/{draft_id}/revisions")))["revisions"]
    assert after == before


def test_unsupported_file_is_rejected(client, project):
    draft_id = _draft(client, project)
    resp = _import(client, project, draft_id, b"a,b\n", filename="map.csv")
    assert resp.status_code == 400


def test_import_project_db_as_geopackage(client, project, tmp_path):
    draft_id = _draft(client, project)
    _import(client, project, draft_id, SAMPLE_KML.read_bytes())
    assert client.post(_url(project, f"/drama-drafts/{draft_id}/confirm"), content="note: 取り込み\n").status_code == 200
    project_db = Path(tmp_path) / "TEST_PROJECT_00" / "project.db"

    draft_id = parse_yaml(client.post(_url(project, "/drama-drafts"), content="title: 続編\n"))["draft_id"]
    resp = _import(client, project, draft_id, project_db.read_bytes(), "project.gpkg", SEQUEL_ID)
    assert resp.status_code == 200, resp.text
    result = parse_yaml(resp)
    # 場所・移動はidで同じものを更新する(プロジェクトの場所は増えない)。project.dbに補助情報は無い
    assert (result["locations_created"], result["locations_updated"]) == (0, 11)
    assert (result["site_flows_created"], result["site_flows_updated"]) == (0, 7)
    assert result["auxiliary_layers"] == {}
    content = _content(client, project, draft_id)
    assert len(content["locations"]) == 11
    assert _flows(content, SEQUEL_ID) == _flows(content, GUIDE_ID)
