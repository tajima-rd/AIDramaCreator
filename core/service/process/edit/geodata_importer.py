# core/service/process/edit/geodata_importer.py
"""
場所の地図(KML・KMZ・GeoPackage)を、作品ごとに下書きへ取り込む(2026-10-02ユーザー決定)。

- 場所(Location)・移動(SiteFlow)の実体はプロジェクトに入り、作品はファイルにあるものを参照する
  (作品のlocations・site_flowsの参照はファイルの内容で置き換える。プロジェクトの実体は消さない)。
- 場所: 属性idが下書きにある場所のidなら、その場所を更新する。無ければ新しい場所(idを書いていればそのidで)。
  name・形はファイルの値にし、address・instruction・descriptionは、ファイルにその属性があれば値(空ならnull)にする。
  属性の名前は大文字・小文字を区別しない(GDALで変換したGeoPackageの「Name」等)。
- 移動: 線の始点・終点を含む場所(ファイルの場所の面)をorigin・destinationにする。どの面にも入らない・2つ以上の面に入る
  端点があれば、取り込み全体を断る(ValueError。下書きは変わらない)。属性idが下書きにある移動のidならその移動を、
  無ければ、この作品の移動のうちoriginとdestinationが同じもの(並びの順に1つずつ)を更新する。どれにも当たらなければ新しい移動。
  name・形・directionはファイルの値にする(directionはファイルにその属性があるとき。空ならnull)。
- 補助情報(場所・移動以外の層)は、ここでは扱わない(Geodata.auxiliaryを呼ぶ側がDatasetにする)。
- 部分YAMLの組み立て(build_patch)は、地図の画面の保存(location_map_editor)も使う(画面の地図の状態を取り込むのと同じ)。
"""

import uuid
from typing import Any, Optional

import yaml
from shapely.geometry.base import BaseGeometry

from core.gis.analysis.containment import areas_covering, line_endpoints
from core.gis.feature import Feature
from core.gis.geometry import is_areal, normalize_wkt, parse_wkt
from core.infra.io.geodata_reader import Geodata, read_geodata
from core.model.drama import SiteFlowDirection
from core.service.process.edit import drama_draft_editor

_OPTIONAL_FIELDS = ("address", "instruction", "description")


class GeodataImportResult:
    """取り込みの結果。revisionは下書きの履歴の番号、auxiliaryは補助情報の層(呼ぶ側がDatasetにする)。"""

    def __init__(
        self,
        revision: int,
        locations_created: int,
        locations_updated: int,
        site_flows_created: int,
        site_flows_updated: int,
        auxiliary: dict[str, list[Feature]],
        dramaturgy_title: str,
    ):
        self.revision: int = revision
        self.locations_created: int = locations_created
        self.locations_updated: int = locations_updated
        self.site_flows_created: int = site_flows_created
        self.site_flows_updated: int = site_flows_updated
        self.auxiliary: dict[str, list[Feature]] = auxiliary
        self.dramaturgy_title: str = dramaturgy_title


def _field(attributes: dict[str, Any], name: str) -> Optional[str]:
    """属性の名前(大文字・小文字を区別しない。GDALの書き出しの「Name」等)。無ければNone。"""
    return next((k for k in attributes if k.lower() == name), None)


def _has(attributes: dict[str, Any], name: str) -> bool:
    return _field(attributes, name) is not None


def _text(attributes: dict[str, Any], name: str) -> Optional[str]:
    field = _field(attributes, name)
    value = attributes.get(field) if field is not None else None
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _label(attributes: dict[str, Any], index: int, kind: str) -> str:
    return f"{kind}{index + 1}件目" + (f"「{_text(attributes, 'name')}」" if _text(attributes, "name") else "")


def _new_key(prefix: str, used: set[str]) -> str:
    """下書きのkeyと重ならない、取り込みの間だけ使うkey。"""
    n = 1
    while f"{prefix}_{n:03d}" in used:
        n += 1
    key = f"{prefix}_{n:03d}"
    used.add(key)
    return key


def import_geodata(
    db_path: str, draft_id: str, dramaturgy_id: str, filename: str, data: bytes
) -> GeodataImportResult:
    """ファイル(filenameの拡張子で形式を決める)を、下書きの作品dramaturgy_idに取り込む。問題があればValueError。"""
    geodata = read_geodata(filename, data)
    if not geodata.locations:
        raise ValueError("ファイルにLocationの層(フォルダ)が無いか、空です")
    content, dramaturgy = load_dramaturgy(db_path, draft_id, dramaturgy_id)
    patch, counts = build_patch(content, dramaturgy, geodata, "imported")
    revision = drama_draft_editor.import_yaml(
        db_path, draft_id, yaml.safe_dump(patch, allow_unicode=True, sort_keys=False)
    )
    return GeodataImportResult(revision, *counts, geodata.auxiliary, dramaturgy.get("title", ""))


def load_dramaturgy(
    db_path: str, draft_id: str, dramaturgy_id: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """下書きの中身(モデル定義YAMLの対応表)と、その中の作品dramaturgy_id。作品が無ければValueError。"""
    content = yaml.safe_load(drama_draft_editor.draft_yaml(db_path, draft_id)) or {}
    dramaturgy = next(
        (d for d in content.get("dramaturgies", []) if d.get("id") == dramaturgy_id), None
    )
    if dramaturgy is None:
        raise ValueError(f"下書きに作品(id '{dramaturgy_id}')がありません")
    return content, dramaturgy


def build_patch(
    content: dict[str, Any],
    dramaturgy: dict[str, Any],
    geodata: Geodata,
    key_prefix: str,
    failure: str = "取り込めませんでした",
) -> tuple[dict[str, Any], tuple[int, int, int, int]]:
    """
    geodataの場所・移動を作品に入れる部分YAMLと、件数(場所の新規・更新、移動の新規・更新)。新しい場所・移動のkeyは
    「<key_prefix>_location_001」等。問題があればValueError(failureの文に続けて、すべての問題を並べる)。
    """
    errors: list[str] = []
    used_keys = {
        item["key"]
        for section in ("locations", "site_flows")
        for item in content.get(section, [])
        if item.get("key")
    }
    existing_locations = {item["id"]: item for item in content.get("locations", []) if item.get("id")}

    # 場所
    location_patches: list[dict[str, Any]] = []
    location_refs: list[str] = []  # ファイルの場所の順のkey
    areas: list[tuple[tuple[str, str], BaseGeometry]] = []  # ((key, 表示の名前), 面)
    created = updated = 0
    for index, (wkt, attributes) in enumerate(geodata.locations):
        label = _label(attributes, index, "Location")
        name = _text(attributes, "name")
        if name is None:
            errors.append(f"{label}: 名前(name)がありません")
            continue
        try:
            geometry = normalize_wkt(wkt, label)
        except ValueError as e:
            errors.append(str(e))
            continue
        item: dict[str, Any] = {"name": name, "geometry": geometry}
        for field in _OPTIONAL_FIELDS:
            if _has(attributes, field):
                item[field] = _text(attributes, field)
        location_id = _text(attributes, "id")
        if location_id in existing_locations:
            key = existing_locations[location_id]["key"]
            item["id"] = location_id
            updated += 1
        else:
            if location_id is not None:
                try:
                    uuid.UUID(location_id)
                except ValueError:
                    errors.append(f"{label}: idがUUIDではありません({location_id})")
                    continue
                item["id"] = location_id
            key = _new_key(f"{key_prefix}_location", used_keys)
            item["key"] = key
            created += 1
        location_patches.append(item)
        location_refs.append(key)
        if geometry is not None:
            shape = parse_wkt(geometry, label)
            if is_areal(shape):
                areas.append(((key, name), shape))

    # 移動
    existing_flows = {item["id"]: item for item in content.get("site_flows", []) if item.get("id")}
    flow_keys = {item["key"]: item for item in content.get("site_flows", []) if item.get("key")}
    dramaturgy_flows = [
        flow_keys[ref["ref"]] for ref in dramaturgy.get("site_flows", []) if ref.get("ref") in flow_keys
    ]
    matched: set[str] = set()
    flow_patches: list[dict[str, Any]] = []
    flow_refs: list[str] = []
    flows_created = flows_updated = 0
    for index, (wkt, attributes) in enumerate(geodata.site_flows):
        label = _label(attributes, index, "SiteFlow")
        try:
            geometry = normalize_wkt(wkt, label, ("LineString",))
        except ValueError as e:
            errors.append(str(e))
            continue
        if geometry is None:
            errors.append(f"{label}: 線がありません")
            continue
        ends = []
        for end_label, point in zip(("始点", "終点"), line_endpoints(parse_wkt(geometry, label)), strict=True):
            hits = areas_covering(point, areas)
            if len(hits) != 1:
                where = "どのLocationの面にも入っていません" if not hits else (
                    "2つ以上のLocationの面に入っています(" + "・".join(n for _, n in hits) + ")"
                )
                errors.append(f"{label}: 線の{end_label}が{where}")
            ends.append(hits[0][0] if len(hits) == 1 else None)
        direction = None
        if _has(attributes, "direction"):
            direction = _text(attributes, "direction")
            if direction is not None and direction not in {d.value for d in SiteFlowDirection}:
                errors.append(f"{label}: directionはforward・backward・bothのどれかにしてください({direction})")
        if None in ends:
            continue
        origin, destination = ends
        item = {
            "name": _text(attributes, "name"),
            "geometry": geometry,
            "origin": {"ref": origin},
            "destination": {"ref": destination},
        }
        if _has(attributes, "direction"):
            item["direction"] = direction
        flow_id = _text(attributes, "id")
        same = existing_flows.get(flow_id) if flow_id else None
        if same is None:
            same = next(
                (
                    f
                    for f in dramaturgy_flows
                    if f["id"] not in matched
                    and f.get("origin", {}).get("ref") == origin
                    and f.get("destination", {}).get("ref") == destination
                ),
                None,
            )
        if same is not None:
            matched.add(same["id"])
            item["id"] = same["id"]
            key = same["key"]
            flows_updated += 1
        else:
            if flow_id is not None:
                try:
                    uuid.UUID(flow_id)
                except ValueError:
                    errors.append(f"{label}: idがUUIDではありません({flow_id})")
                    continue
                item["id"] = flow_id
            key = _new_key(f"{key_prefix}_site_flow", used_keys)
            item["key"] = key
            flows_created += 1
        flow_patches.append(item)
        flow_refs.append(key)

    if errors:
        raise ValueError(f"{failure}:\n" + "\n".join(f"- {e}" for e in errors))
    patch = {
        "locations": location_patches,
        "site_flows": flow_patches,
        "dramaturgies": [
            {
                "id": dramaturgy["id"],
                "locations": [{"ref": key} for key in location_refs],
                "site_flows": [{"ref": key} for key in flow_refs],
            }
        ],
    }
    return patch, (created, updated, flows_created, flows_updated)
