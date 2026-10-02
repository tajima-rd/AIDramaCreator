# core/infra/io/geodata_reader.py
"""
場所の地図のファイル(KML・KMZ・GeoPackage)を読み、場所(Location)・移動(SiteFlow)・補助情報の層に分ける
(2026-10-02ユーザー決定。形の決まりはapps/AIDC-Console/templates/README.md)。ファイル形式の読み取りはcore.gis.io。

- 層(KMLのフォルダ・GeoPackageの地物の表)の名前が、大文字・小文字と「_」・空白を無視して「location」のものが場所、
  「siteflow」のものが移動。それ以外の層はすべて補助情報(Google マイマップはフォルダを入れ子にできないため)。
- KMLでどのフォルダにも入っていないPlacemarkは補助情報(層の名前は「補助情報」)。KMZは中の最初のKML(doc.kmlがあればそれ)を読む。
- GeoPackageは地物の表をすべて読む。座標はWGS84(KMLの決まり。GeoPackageもWGS84のものだけを扱う)。
"""

import os
import tempfile
from typing import Optional

from core.gis.feature import Feature
from core.gis.io.geopackage import read_feature_tables
from core.gis.io.kml import kml_in_kmz, read_kml_layers

AUXILIARY_LAYER = "補助情報"  # KMLでどのフォルダにも入っていないPlacemarkの層
KML_SUFFIXES = (".kml", ".xml")  # Google マイマップの書き出しを.xmlで保存したものも読む
KMZ_SUFFIX = ".kmz"
GEOPACKAGE_SUFFIX = ".gpkg"
GEODATA_SUFFIXES = (*KML_SUFFIXES, KMZ_SUFFIX, GEOPACKAGE_SUFFIX)

_LOCATION = "location"
_SITE_FLOW = "siteflow"


class Geodata:
    """読んだ地図。locations・site_flowsは場所・移動の層の地物(層が複数あればつなげる)、auxiliaryは補助情報の層(層の名前→地物)。"""

    def __init__(
        self,
        locations: list[Feature],
        site_flows: list[Feature],
        auxiliary: dict[str, list[Feature]],
    ):
        self.locations: list[Feature] = locations
        self.site_flows: list[Feature] = site_flows
        self.auxiliary: dict[str, list[Feature]] = auxiliary


def _layer_kind(name: str) -> Optional[str]:
    normalized = name.lower().replace("_", "").replace(" ", "")
    return normalized if normalized in (_LOCATION, _SITE_FLOW) else None


def _split(layers: dict[str, list[Feature]]) -> Geodata:
    locations: list[Feature] = []
    site_flows: list[Feature] = []
    auxiliary: dict[str, list[Feature]] = {}
    for name, features in layers.items():
        kind = _layer_kind(name)
        if kind == _LOCATION:
            locations.extend(features)
        elif kind == _SITE_FLOW:
            site_flows.extend(features)
        elif features:
            auxiliary.setdefault(name, []).extend(features)
    return Geodata(locations, site_flows, auxiliary)


def read_geodata(filename: str, data: bytes) -> Geodata:
    """ファイル名の拡張子で形式を決めて読む。読めなければValueError。"""
    suffix = os.path.splitext(filename)[1].lower()
    if suffix in KML_SUFFIXES:
        return _split(read_kml_layers(data, AUXILIARY_LAYER))
    if suffix == KMZ_SUFFIX:
        return _split(read_kml_layers(kml_in_kmz(data), AUXILIARY_LAYER))
    if suffix == GEOPACKAGE_SUFFIX:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "import.gpkg")
            with open(path, "wb") as f:
                f.write(data)
            return _split(read_feature_tables(path))
    raise ValueError(f"取り込めるのは{'・'.join(GEODATA_SUFFIXES)}のファイルです: {filename}")
