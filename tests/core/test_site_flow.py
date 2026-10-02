# tests/core/test_site_flow.py
"""
場所の形(Location.geometry)・場所の間の移動(SiteFlow)・作品の場所と移動の参照と、それを持つproject.db(GeoPackage)。
tmp_pathの中のproject.dbだけを使う。
"""

import shutil
import sqlite3
import subprocess

import pytest

from core.infra.io.model_definition_reader import build_model_definition_from_yaml
from core.infra.io.model_definition_writer import model_definition_to_yaml
from core.gis.io.geopackage import decode_geometry, encode_geometry
from core.model.drama import SiteFlowDirection
from core.service.process.edit import drama_draft_editor as editor

# 2つの面の場所と、その間の移動。作品は場所2つと移動を参照する。参照しない場所(点)もある
MODEL = """
locations:
  - key: gate
    name: 最初の場所
    geometry: POLYGON((0 0, 2 0, 2 2, 0 2, 0 0))
    instruction: スキー場の説明をする
  - key: slope
    name: 急なエリア
    geometry: POLYGON ((10 0, 12 0, 12 2, 10 2, 10 0))
  - key: station
    name: 駅
    geometry: POINT Z (5 5 0)
site_flows:
  - key: gate_to_slope
    name: リフトで上がる
    geometry: LINESTRING (1 1, 6 3, 11 1)
    direction: forward
    origin: {ref: gate}
    destination: {ref: slope}
  - key: no_line
    origin: {ref: slope}
    destination: {ref: gate}
dramaturgy:
  title: スキー場ガイド
  locations: [{ref: gate}, {ref: slope}]
  site_flows: [{ref: gate_to_slope}]
"""


def test_site_flow_and_dramaturgy_references_are_built():
    definition = build_model_definition_from_yaml(MODEL)
    gate, slope, station = definition.locations
    flow = definition.site_flows[0]
    assert (flow.origin, flow.destination, flow.direction) == (gate, slope, SiteFlowDirection.FORWARD)
    assert definition.site_flows[1].direction is None
    dramaturgy = definition.dramaturgy
    assert dramaturgy.locations == [gate, slope]
    assert dramaturgy.site_flows == [flow]
    # WKTは正規化する(書き方をそろえ、Z座標は捨てる)
    assert gate.geometry == "POLYGON ((0 0, 2 0, 2 2, 0 2, 0 0))"
    assert station.geometry == "POINT (5 5)"


def test_model_with_site_flows_round_trips_through_yaml():
    text = model_definition_to_yaml(build_model_definition_from_yaml(MODEL))
    assert model_definition_to_yaml(build_model_definition_from_yaml(text)) == text


@pytest.mark.parametrize(
    "line, message",
    [
        ("LINESTRING (5 5, 11 1)", "始点"),
        ("LINESTRING (1 1, 5 5)", "終点"),
    ],
)
def test_site_flow_endpoint_outside_its_location_is_rejected(line, message):
    text = MODEL.replace("LINESTRING (1 1, 6 3, 11 1)", line)
    with pytest.raises(ValueError, match=message):
        build_model_definition_from_yaml(text)


@pytest.mark.parametrize(
    "old, new, message",
    [
        ("LINESTRING (1 1, 6 3, 11 1)", "POINT (1 1)", "LineString"),
        ("POINT Z (5 5 0)", "POINT (5", "読めません"),
    ],
)
def test_invalid_geometry_is_rejected(old, new, message):
    with pytest.raises(ValueError, match=message):
        build_model_definition_from_yaml(MODEL.replace(old, new))


def test_geopackage_blob_round_trips():
    wkt = "POLYGON ((134.5577669 35.4044282, 134.5602506 35.4052458, 134.55 35.41, 134.5577669 35.4044282))"
    blob = encode_geometry(wkt)
    assert blob[:2] == b"GP"
    assert decode_geometry(blob) == wkt
    assert encode_geometry(None) is None and decode_geometry(None) is None


@pytest.fixture
def db_path(tmp_path) -> str:
    return str(tmp_path / "TEST_PROJECT_00" / "project.db")


def _confirm(db_path: str, yaml_text: str) -> None:
    draft = editor.create_draft(db_path, "取り込み")
    editor.import_yaml(db_path, draft.id, yaml_text)
    editor.confirm_draft(db_path, draft.id, "取り込み")


def test_site_flows_round_trip_through_project_db(db_path):
    expected = model_definition_to_yaml(build_model_definition_from_yaml(MODEL))  # idを決めておく
    _confirm(db_path, expected)
    assert model_definition_to_yaml(editor.load_model(db_path)) == expected


def test_project_db_is_a_geopackage(db_path):
    _confirm(db_path, MODEL)
    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("PRAGMA application_id").fetchone()[0] == 0x47504B47
        assert conn.execute(
            "SELECT table_name, data_type, srs_id FROM gpkg_contents ORDER BY table_name"
        ).fetchall() == [("location", "features", 4326), ("site_flow", "features", 4326)]
        assert conn.execute(
            "SELECT table_name, column_name, geometry_type_name FROM gpkg_geometry_columns ORDER BY table_name"
        ).fetchall() == [("location", "geom", "GEOMETRY"), ("site_flow", "geom", "LINESTRING")]
    finally:
        conn.close()


@pytest.mark.skipif(shutil.which("ogrinfo") is None, reason="GDAL(ogrinfo)が無い")
def test_gdal_reads_locations_and_site_flows_from_project_db(db_path):
    _confirm(db_path, MODEL)
    output = subprocess.run(
        ["ogrinfo", "-ro", "-al", "-so", db_path], capture_output=True, text=True, check=True
    ).stdout
    assert "Layer name: location" in output and "Layer name: site_flow" in output
    assert "Feature Count: 3" in output and "Feature Count: 2" in output
