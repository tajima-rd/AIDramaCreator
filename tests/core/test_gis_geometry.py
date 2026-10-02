"""core.gis.geometry(WKTの正規化とGeoJSONとの変換)・core.gis.analysis.containment(点を含む面)。"""

import pytest

from core.gis.analysis.containment import areas_covering, line_endpoints
from core.gis.geometry import geojson_to_wkt, normalize_wkt, parse_wkt, wkt_to_geojson

SQUARE = "POLYGON ((134.5 35.4, 134.6 35.4, 134.6 35.5, 134.5 35.5, 134.5 35.4))"


def test_geojson_round_trip_keeps_lon_lat_order():
    geojson = wkt_to_geojson(SQUARE, "面")
    assert geojson["type"] == "Polygon"
    assert geojson["coordinates"][0][0] == [134.5, 35.4]  # 経度・緯度の順(リスト)
    assert geojson_to_wkt(geojson, "面") == normalize_wkt(SQUARE, "面")


def test_geojson_drops_z_and_rejects_broken_input():
    line = {"type": "LineString", "coordinates": [[134.5, 35.4, 10], [134.6, 35.5, 0]]}
    assert geojson_to_wkt(line, "線") == "LINESTRING (134.5 35.4, 134.6 35.5)"
    assert wkt_to_geojson(None, "x") is None and geojson_to_wkt(None, "x") is None
    with pytest.raises(ValueError):
        geojson_to_wkt({"type": "Polygon"}, "面")


def test_areas_covering_includes_boundary():
    area = parse_wkt(SQUARE, "面")
    start, end = line_endpoints(parse_wkt("LINESTRING (134.5 35.45, 134.7 35.45)", "線"))
    assert areas_covering(start, [("a", area)]) == ["a"]  # 境界の上
    assert areas_covering(end, [("a", area)]) == []
