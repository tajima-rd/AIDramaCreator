# core/gis/geometry.py
"""
形(WKTの文字列。座標はWGS84=EPSG:4326、経度・緯度の順)の検査と正規化、GeoJSONとの変換(shapely)。
読み込みのたびに同じ書き方へ正規化するので、保存と読み出しの往復で文字列が変わらない。Z座標は捨てる(KMLの高さ0等)。
"""

from typing import Any, Optional

import shapely
import shapely.geometry
from shapely.geometry.base import BaseGeometry

# 面の形の種類
AREAL_TYPES = ("Polygon", "MultiPolygon")


def parse_wkt(text: str, where: str) -> BaseGeometry:
    """WKTを読む。読めなければValueError。"""
    try:
        geometry = shapely.from_wkt(text)
    except shapely.errors.GEOSException as e:
        raise ValueError(f"{where}の形(WKT)が読めません: {e}") from None
    return shapely.force_2d(geometry)


def normalize_wkt(text: Optional[str], where: str, kinds: Optional[tuple[str, ...]] = None) -> Optional[str]:
    """
    WKTを検査し、正規化した文字列にする(Noneと空文字はNone)。kindsを渡すと、形の種類(Point・LineString・Polygon等)を
    その中に限る。
    """
    if text is None or not text.strip():
        return None
    geometry = parse_wkt(text, where)
    if geometry.is_empty:
        raise ValueError(f"{where}の形(WKT)が空です")
    if kinds is not None and geometry.geom_type not in kinds:
        raise ValueError(f"{where}の形は{'・'.join(kinds)}にしてください(今は{geometry.geom_type})")
    return to_wkt(geometry)


def to_wkt(geometry: BaseGeometry) -> str:
    """形を、正規化したWKTにする(桁は丸めない)。"""
    return shapely.to_wkt(geometry, rounding_precision=-1, trim=True)


def is_areal(geometry: BaseGeometry) -> bool:
    """面(Polygon・MultiPolygon)か。"""
    return geometry.geom_type in AREAL_TYPES


def wkt_to_geojson(text: Optional[str], where: str) -> Optional[dict[str, Any]]:
    """WKTを、GeoJSONの形(geometry)の辞書にする(Noneと空文字はNone)。座標はリスト(JSON・YAMLにそのまま書ける)。"""
    if text is None or not text.strip():
        return None
    return _as_lists(shapely.geometry.mapping(parse_wkt(text, where)))


def _as_lists(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return [_as_lists(v) for v in value]
    if isinstance(value, dict):
        return {k: _as_lists(v) for k, v in value.items()}
    return value


def geojson_to_wkt(geojson: Optional[dict[str, Any]], where: str) -> Optional[str]:
    """GeoJSONの形(geometry)の辞書を、正規化したWKTにする(NoneはNone)。読めなければValueError。"""
    if geojson is None:
        return None
    try:
        geometry = shapely.geometry.shape(geojson)
    except (KeyError, TypeError, ValueError, AttributeError, shapely.errors.GEOSException) as e:
        raise ValueError(f"{where}の形(GeoJSON)が読めません: {e}") from None
    return normalize_wkt(to_wkt(shapely.force_2d(geometry)), where)
