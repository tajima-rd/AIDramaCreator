# core/service/process/edit/location_map_editor.py
"""
地図の画面(Edit > Edit Location on Map)で、作品の場所(Location)・移動(SiteFlow)を編集する(2026-10-02ユーザー決定)。
形は画面とGeoJSONでやり取りし、モデルにはWKTで入れる(core.gis.geometry)。

- 読み出し(read_map): 下書きの作品が参照する場所・移動と、作品に割り当てた補助情報のDataset(GeoPackage)の地物。
  補助情報は表示だけ(編集しない)。
- 保存(save_map): 画面の地図の状態(形のある場所・移動のすべて)を、地図の取り込みと同じ規則で下書きに入れる
  (geodata_importer.build_patch。直接編集として履歴に積む)。idのある場所・移動は更新、idの無いものは新規。
  移動のorigin・destinationは線の始点・終点を含む場所の面から決め、どの面にも入らない・2つ以上の面に入る端点があれば
  保存全体を断る(ValueError)。画面から消した場所・移動は作品の参照から外す(プロジェクトの実体は消さない)。
  形の無い場所・移動は地図に出ないので、作品の参照をそのまま残す。
"""

import os
from typing import Any, Optional

import yaml

from core.gis.feature import Feature
from core.gis.geometry import geojson_to_wkt, wkt_to_geojson
from core.gis.io.geopackage import read_feature_tables
from core.infra.io.geodata_reader import Geodata
from core.infra.store.dataset_registry_store import list_dataset_entries
from core.service.process.edit import drama_draft_editor
from core.service.process.edit.geodata_importer import build_patch, load_dramaturgy

LOCATION_FIELDS = ("name", "address", "instruction", "description")
SITE_FLOW_FIELDS = ("name", "direction")
_GEOPACKAGE_SUFFIX = ".gpkg"


class AuxiliaryLayer:
    """補助情報の層。featuresは(形(GeoJSON。無ければNone), 属性)。"""

    def __init__(self, dataset_filename: str, layer: str, features: list[tuple[Optional[dict], dict]]):
        self.dataset_filename: str = dataset_filename
        self.layer: str = layer
        self.features: list[tuple[Optional[dict], dict]] = features


class LocationMap:
    """作品の地図。locations・site_flowsは対応表(形はGeoJSON)、auxiliaryは補助情報の層、warningsは読めなかったDataset等。"""

    def __init__(
        self,
        dramaturgy_title: str,
        locations: list[dict[str, Any]],
        site_flows: list[dict[str, Any]],
        auxiliary: list[AuxiliaryLayer],
        warnings: list[str],
    ):
        self.dramaturgy_title: str = dramaturgy_title
        self.locations: list[dict[str, Any]] = locations
        self.site_flows: list[dict[str, Any]] = site_flows
        self.auxiliary: list[AuxiliaryLayer] = auxiliary
        self.warnings: list[str] = warnings


class MapSaveResult:
    def __init__(self, revision: int, counts: tuple[int, int, int, int]):
        self.revision: int = revision
        (
            self.locations_created,
            self.locations_updated,
            self.site_flows_created,
            self.site_flows_updated,
        ) = counts


def _work_items(content: dict[str, Any], dramaturgy: dict[str, Any], section: str) -> list[dict[str, Any]]:
    """作品が参照する場所・移動(作品の並びの順)。"""
    by_key = {item["key"]: item for item in content.get(section, []) if item.get("key")}
    return [by_key[ref["ref"]] for ref in dramaturgy.get(section, []) if ref.get("ref") in by_key]


def _scene_location_keys(dramaturgy: dict[str, Any]) -> set[str]:
    return {
        (scene.get("location") or {}).get("ref")
        for act in dramaturgy.get("acts", [])
        for scene in act.get("scenes", [])
        if scene.get("location")
    }


def read_map(db_path: str, datasets_dir: str, draft_id: str, dramaturgy_id: str) -> LocationMap:
    content, dramaturgy = load_dramaturgy(db_path, draft_id, dramaturgy_id)
    locations = _work_items(content, dramaturgy, "locations")
    ids = {item["key"]: item.get("id") for item in content.get("locations", []) if item.get("key")}
    used = _scene_location_keys(dramaturgy)
    location_rows = [
        {
            "id": item.get("id"),
            **{field: item.get(field) for field in LOCATION_FIELDS},
            "geometry": wkt_to_geojson(item.get("geometry"), f"場所「{item.get('name')}」"),
            "used_in_scenes": item.get("key") in used,
        }
        for item in locations
    ]
    flow_rows = [
        {
            "id": item.get("id"),
            **{field: item.get(field) for field in SITE_FLOW_FIELDS},
            "geometry": wkt_to_geojson(item.get("geometry"), f"移動「{item.get('name') or ''}」"),
            "origin_id": ids.get((item.get("origin") or {}).get("ref")),
            "destination_id": ids.get((item.get("destination") or {}).get("ref")),
        }
        for item in _work_items(content, dramaturgy, "site_flows")
    ]
    auxiliary, warnings = _read_auxiliary(db_path, datasets_dir, dramaturgy_id)
    return LocationMap(dramaturgy.get("title") or "", location_rows, flow_rows, auxiliary, warnings)


def _read_auxiliary(
    db_path: str, datasets_dir: str, dramaturgy_id: str
) -> tuple[list[AuxiliaryLayer], list[str]]:
    """作品に割り当てたGeoPackageのDatasetの、すべての地物の層。読めないものはwarningsに書いて飛ばす。"""
    layers: list[AuxiliaryLayer] = []
    warnings: list[str] = []
    for entry in list_dataset_entries(db_path):
        filename = entry["filename"]
        if entry["drama_id"] != dramaturgy_id or not filename.lower().endswith(_GEOPACKAGE_SUFFIX):
            continue
        path = os.path.join(datasets_dir, filename)
        try:
            tables = read_feature_tables(path)
            for layer, features in tables.items():
                layers.append(
                    AuxiliaryLayer(
                        filename,
                        layer,
                        [
                            (wkt_to_geojson(wkt, f"{filename}の{layer}"), _plain(attributes))
                            for wkt, attributes in features
                        ],
                    )
                )
        except (OSError, ValueError) as e:
            warnings.append(f"補助情報のDataset「{filename}」を読めません: {e}")
    return layers, warnings


def _plain(attributes: dict[str, Any]) -> dict[str, Any]:
    """属性の値を、画面に渡せる値(文字列・数・None)にする。"""
    return {
        name: value if value is None or isinstance(value, (str, int, float)) else str(value)
        for name, value in attributes.items()
    }


def _features(items: list[dict[str, Any]], fields: tuple[str, ...], kind: str) -> list[Feature]:
    features: list[Feature] = []
    for index, item in enumerate(items):
        label = f"{kind}{index + 1}件目" + (f"「{item['name']}」" if item.get("name") else "")
        attributes: dict[str, Any] = {field: item.get(field) for field in fields}
        if item.get("id"):
            attributes["id"] = item["id"]
        features.append((geojson_to_wkt(item.get("geometry"), label), attributes))
    return features


def save_map(
    db_path: str,
    draft_id: str,
    dramaturgy_id: str,
    locations: list[dict[str, Any]],
    site_flows: list[dict[str, Any]],
) -> MapSaveResult:
    """
    画面の地図の状態(locations・site_flowsは対応表。形はGeoJSON、idの無いものは新規)を下書きの作品に入れる。
    問題があればValueError(下書きは変わらない)。
    """
    content, dramaturgy = load_dramaturgy(db_path, draft_id, dramaturgy_id)
    geodata = Geodata(
        _features(locations, LOCATION_FIELDS, "Location"),
        _features(site_flows, SITE_FLOW_FIELDS, "SiteFlow"),
        {},
    )
    patch, counts = build_patch(content, dramaturgy, geodata, "map", "地図を保存できませんでした")
    # 形の無い場所・移動は地図に出ないので、作品の参照を残す
    work_patch = patch["dramaturgies"][0]
    for section in ("locations", "site_flows"):
        refs = work_patch[section]
        kept = {ref["ref"] for ref in refs}
        for item in _work_items(content, dramaturgy, section):
            if not item.get("geometry") and item["key"] not in kept:
                refs.append({"ref": item["key"]})
    revision = drama_draft_editor.edit_draft(
        db_path, draft_id, yaml.safe_dump(patch, allow_unicode=True, sort_keys=False)
    )
    return MapSaveResult(revision, counts)
