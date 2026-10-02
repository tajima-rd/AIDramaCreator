# tests/core/test_geodata_reader.py
"""場所の地図の読み取り(core.infra.io.geodata_reader)。KMLの入れ子のフォルダ・SchemaData・MultiGeometry・KMZと、GeoPackage。"""

import io
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from core.infra.io.geodata_reader import read_geodata
from core.gis.io.geopackage import read_feature_tables, write_feature_layers
from tests.conftest import REPO_ROOT

SAMPLE_KML = Path(REPO_ROOT) / "apps" / "sample_data" / "ハチ北スキー場ガイド" / "ハチ北スキー場.kml"

KML = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
  <Folder><name>location</name>
    <Placemark><name>広場</name><description>表示用の説明(読まない)</description>
      <ExtendedData><SchemaData schemaUrl="#s"><SimpleData name="instruction">案内</SimpleData></SchemaData></ExtendedData>
      <Polygon><outerBoundaryIs><LinearRing><coordinates>0,0,0 2,0,0 2,2,0 0,2,0 0,0,0</coordinates></LinearRing></outerBoundaryIs>
        <innerBoundaryIs><LinearRing><coordinates>0.5,0.5 1,0.5 1,1 0.5,0.5</coordinates></LinearRing></innerBoundaryIs></Polygon>
    </Placemark>
  </Folder>
  <Folder><name>Site Flow</name>
    <Placemark><name>道</name><ExtendedData><Data name="direction"><value>both</value></Data></ExtendedData>
      <LineString><coordinates>1,1 5,5</coordinates></LineString></Placemark>
  </Folder>
  <Folder><name>補助情報</name>
    <Folder><name>リフト</name>
      <Placemark><name>A</name><MultiGeometry><LineString><coordinates>0,0 1,1</coordinates></LineString>
        <LineString><coordinates>1,1 2,2</coordinates></LineString></MultiGeometry></Placemark>
    </Folder>
  </Folder>
  <Placemark><name>どこにも入らない点</name><Point><coordinates>9,9</coordinates></Point></Placemark>
</Document></kml>
""".encode()


def test_kml_layers_are_split_by_folder():
    geodata = read_geodata("map.kml", KML)
    (wkt, attributes), = geodata.locations
    assert wkt == "POLYGON ((0 0, 2 0, 2 2, 0 2, 0 0), (0.5 0.5, 1 0.5, 1 1, 0.5 0.5))"
    assert attributes == {"name": "広場", "instruction": "案内"}  # <description>は読まない
    assert geodata.site_flows == [("LINESTRING (1 1, 5 5)", {"name": "道", "direction": "both"})]
    # 入れ子のフォルダは、Placemarkを直接含むフォルダの名前の層。フォルダの外は「補助情報」
    assert geodata.auxiliary == {
        "リフト": [("MULTILINESTRING ((0 0, 1 1), (1 1, 2 2))", {"name": "A"})],
        "補助情報": [("POINT (9 9)", {"name": "どこにも入らない点"})],
    }


def test_kmz_reads_doc_kml():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("doc.kml", KML)
    assert len(read_geodata("map.kmz", buffer.getvalue()).locations) == 1


def test_broken_files_are_rejected():
    with pytest.raises(ValueError, match="KMLとして読めません"):
        read_geodata("map.kml", b"<kml")
    with pytest.raises(ValueError, match="GeoPackageとして読めません"):
        read_geodata("map.gpkg", b"not a geopackage")


def test_geopackage_layers_round_trip(tmp_path):
    path = str(tmp_path / "layers.gpkg")
    layers = {"施設": [("POLYGON ((0 0, 1 0, 1 1, 0 0))", {"name": "トイレ", "description": None})], "点": [("POINT (1 2)", {"名前": "x"})]}
    write_feature_layers(path, layers)
    assert read_feature_tables(path) == layers


@pytest.mark.skipif(shutil.which("ogr2ogr") is None, reason="GDAL(ogr2ogr)が無い")
def test_geopackage_converted_by_gdal_is_read(tmp_path):
    path = tmp_path / "converted.gpkg"
    subprocess.run(["ogr2ogr", "-f", "GPKG", str(path), str(SAMPLE_KML)], check=True, capture_output=True)
    geodata = read_geodata("converted.gpkg", path.read_bytes())
    assert (len(geodata.locations), len(geodata.site_flows)) == (11, 7)
    assert set(geodata.auxiliary) == {"リフト乗降場所", "リフト", "施設", "チケット売り場", "参照"}
