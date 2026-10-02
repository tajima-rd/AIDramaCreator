# tests/api/test_location_map.py
"""
地図の画面の読み出し・保存(GET・POST /projects/{id}/drama-drafts/{draft_id}/map)の結合テスト。
サンプルはapps/sample_data/ハチ北スキー場ガイド/ハチ北スキー場.kml(Location 11・SiteFlow 7・補助情報5層)を取り込んで使う。

- 読み出しは、作品の場所・移動の形をGeoJSON(経度・緯度の順)で返し、補助情報のDatasetの層も返すこと
- 読み出したものをそのまま保存しても、中身が変わらないこと(すべて更新、新規なし)
- 新しい面・線を足すと、線の端点を含む面から移動のorigin・destinationが決まること
- 送らなかった場所・移動は作品の参照から外れ、プロジェクトの実体は残ること。形の無い場所は参照に残ること
- 線の端点がどの面にも入らなければ、保存全体を断ること(下書きは変わらない)
"""

import copy

import shapely
import shapely.geometry
import yaml

from tests.api.test_geodata_import import GUIDE_ID, SAMPLE_KML, _content, _draft, _import, _url
from tests.conftest import parse_yaml


def _map(client, project, draft_id) -> dict:
    resp = client.get(_url(project, f"/drama-drafts/{draft_id}/map"), params={"dramaturgy_id": GUIDE_ID})
    assert resp.status_code == 200, resp.text
    return parse_yaml(resp)


def _save(client, project, draft_id, locations, site_flows):
    body = yaml.safe_dump(
        {"dramaturgy_id": GUIDE_ID, "locations": locations, "site_flows": site_flows}, allow_unicode=True
    )
    return client.post(_url(project, f"/drama-drafts/{draft_id}/map"), content=body)


def _imported(client, project) -> str:
    draft_id = _draft(client, project)
    assert _import(client, project, draft_id, SAMPLE_KML.read_bytes()).status_code == 200
    return draft_id


def _guide(content: dict) -> dict:
    return next(d for d in content["dramaturgies"] if d["id"] == GUIDE_ID)


def test_read_map(client, project):
    draft_id = _imported(client, project)
    result = _map(client, project, draft_id)
    assert result["dramaturgy_title"] == "ハチ北スキー場ガイド"
    assert len(result["locations"]) == 11 and len(result["site_flows"]) == 7
    kids = next(loc for loc in result["locations"] if loc["name"] == "キッズパーク")
    assert kids["geometry"]["type"] == "Polygon"
    lon, lat = kids["geometry"]["coordinates"][0][0]
    assert 134 < lon < 135 and 35 < lat < 36  # 経度・緯度の順
    ids = {loc["id"] for loc in result["locations"]}
    assert all(f["origin_id"] in ids and f["destination_id"] in ids for f in result["site_flows"])
    layers = {layer["layer"]: len(layer["features"]) for layer in result["auxiliary_layers"]}
    assert layers == {"リフト乗降場所": 20, "リフト": 13, "施設": 22, "チケット売り場": 2, "参照": 2}
    assert result["warnings"] == []


def test_save_unchanged_map_keeps_content(client, project):
    draft_id = _imported(client, project)
    before = _content(client, project, draft_id)
    result = _map(client, project, draft_id)
    resp = _save(client, project, draft_id, result["locations"], result["site_flows"])
    assert resp.status_code == 200, resp.text
    saved = parse_yaml(resp)
    assert (saved["locations_created"], saved["locations_updated"]) == (0, 11)
    assert (saved["site_flows_created"], saved["site_flows_updated"]) == (0, 7)
    after = _content(client, project, draft_id)
    assert after["locations"] == before["locations"]
    assert after["site_flows"] == before["site_flows"]
    assert _guide(after) == _guide(before)


def test_add_polygon_and_line(client, project):
    draft_id = _imported(client, project)
    result = _map(client, project, draft_id)
    kids = next(loc for loc in result["locations"] if loc["name"] == "キッズパーク")
    kids_point = shapely.geometry.shape(kids["geometry"]).representative_point()
    # 既存の場所から離れた正方形の新しい場所と、そこからキッズパークへの線
    x, y = kids_point.x + 0.05, kids_point.y + 0.05
    square = shapely.box(x - 0.001, y - 0.001, x + 0.001, y + 0.001)
    new_location = {
        "name": "新しい場所",
        "instruction": "ここで案内する",
        "geometry": {"type": "Polygon", "coordinates": [list(map(list, square.exterior.coords))]},
    }
    new_flow = {
        "name": "新しい移動",
        "direction": "forward",
        "geometry": {"type": "LineString", "coordinates": [[x, y], [kids_point.x, kids_point.y]]},
    }
    resp = _save(
        client, project, draft_id, [*result["locations"], new_location], [*result["site_flows"], new_flow]
    )
    assert resp.status_code == 200, resp.text
    saved = parse_yaml(resp)
    assert (saved["locations_created"], saved["site_flows_created"]) == (1, 1)

    after = _map(client, project, draft_id)
    added = next(loc for loc in after["locations"] if loc["name"] == "新しい場所")
    assert added["id"] and added["instruction"] == "ここで案内する"
    flow = next(f for f in after["site_flows"] if f["name"] == "新しい移動")
    assert (flow["origin_id"], flow["destination_id"], flow["direction"]) == (added["id"], kids["id"], "forward")


def test_removed_features_leave_the_work_only(client, project):
    draft_id = _imported(client, project)
    result = _map(client, project, draft_id)
    kids = next(loc for loc in result["locations"] if loc["name"] == "キッズパーク")
    locations = [loc for loc in result["locations"] if loc["id"] != kids["id"]]
    flows = [f for f in result["site_flows"] if kids["id"] not in (f["origin_id"], f["destination_id"])]
    assert len(flows) < len(result["site_flows"])
    assert _save(client, project, draft_id, locations, flows).status_code == 200

    after = _map(client, project, draft_id)
    assert kids["id"] not in {loc["id"] for loc in after["locations"]}
    assert len(after["site_flows"]) == len(flows)
    content = _content(client, project, draft_id)
    assert kids["id"] in {loc["id"] for loc in content["locations"]}  # プロジェクトの実体は残る


def test_location_without_shape_stays_in_the_work(client, project):
    draft_id = _imported(client, project)
    refs = _guide(_content(client, project, draft_id))["locations"]  # 参照の一覧は重ねると置き換わる
    patch = {
        "locations": [{"key": "shapeless", "name": "形の無い場所"}],
        "dramaturgies": [{"id": GUIDE_ID, "locations": [*refs, {"ref": "shapeless"}]}],
    }
    resp = client.post(
        _url(project, f"/drama-drafts/{draft_id}/edit"), content=yaml.safe_dump(patch, allow_unicode=True)
    )
    assert resp.status_code == 200, resp.text
    result = _map(client, project, draft_id)
    shapeless = next(loc for loc in result["locations"] if loc["name"] == "形の無い場所")
    assert shapeless["geometry"] is None
    # 画面は形のあるものだけを送る
    shaped = [loc for loc in result["locations"] if loc["geometry"] is not None]
    assert _save(client, project, draft_id, shaped, result["site_flows"]).status_code == 200
    assert "形の無い場所" in {loc["name"] for loc in _map(client, project, draft_id)["locations"]}


def test_line_endpoint_outside_locations_is_refused(client, project):
    draft_id = _imported(client, project)
    before = _content(client, project, draft_id)
    result = _map(client, project, draft_id)
    flows = copy.deepcopy(result["site_flows"])
    coords = flows[0]["geometry"]["coordinates"]
    coords[-1] = [coords[-1][0] + 1.0, coords[-1][1]]  # 終点をどの面にも入らない所へ
    resp = _save(client, project, draft_id, result["locations"], flows)
    assert resp.status_code == 400
    assert "地図を保存できませんでした" in resp.text
    assert "終点がどのLocationの面にも入っていません" in resp.text
    assert _content(client, project, draft_id) == before
