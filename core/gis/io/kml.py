# core/gis/io/kml.py
"""
KML・KMZの読み取り。GDAL(LIBKML)ではなく標準のXMLで読む(LIBKMLはExtendedDataのid・descriptionとKML自体の要素を同じ列にまとめ、
Google マイマップの書き出しで値が混ざるため)。

- 地物はPlacemark。属性は、Placemarkのnameと、ExtendedDataのData・SchemaDataのSimpleData(QGIS等が書き出す形)。
  Placemarkの<description>(Google マイマップが属性から作る説明の表示)は読まない。
- 層は、Placemarkを直接含むフォルダの名前(どのフォルダにも入っていなければ、呼ぶ側が決めた既定の層)。
- 形はWKT(Z座標は捨てる)。座標はWGS84(KMLの決まり)。
"""

import io
import xml.etree.ElementTree as ET
import zipfile
from typing import Any, Optional

import shapely
from shapely.geometry.base import BaseGeometry

from ..feature import Feature
from ..geometry import to_wkt


def kml_in_kmz(data: bytes) -> bytes:
    """KMZ(ZIP)の中の最初のKML(doc.kmlがあればそれ)。読めなければValueError。"""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = [n for n in archive.namelist() if n.lower().endswith(".kml")]
            if not names:
                raise ValueError("KMZの中にKMLがありません")
            name = "doc.kml" if "doc.kml" in names else names[0]
            return archive.read(name)
    except zipfile.BadZipFile:
        raise ValueError("KMZ(ZIP)として読めません") from None


def _local(tag: str) -> str:
    """名前空間を除いた要素の名前。"""
    return tag.rsplit("}", 1)[-1]


def _child(element: ET.Element, name: str) -> Optional[ET.Element]:
    return next((c for c in element if _local(c.tag) == name), None)


def _children(element: ET.Element, name: str) -> list[ET.Element]:
    return [c for c in element if _local(c.tag) == name]


def read_kml_layers(data: bytes, default_layer: str) -> dict[str, list[Feature]]:
    """
    KMLの地物を、それを直接含むフォルダの名前ごとに読む(フォルダの並びの順)。どのフォルダにも入っていない地物は
    default_layerの層にする。読めなければValueError。
    """
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise ValueError(f"KMLとして読めません: {e}") from None
    layers: dict[str, list[Feature]] = {}

    def walk(element: ET.Element, layer: str) -> None:
        for child in element:
            kind = _local(child.tag)
            if kind in ("Document", "Folder"):
                name_element = _child(child, "name")
                name = (name_element.text or "").strip() if name_element is not None else ""
                walk(child, name if kind == "Folder" and name else layer)
            elif kind == "Placemark":
                layers.setdefault(layer, []).append(_placemark(child))

    walk(root, default_layer)
    return layers


def _placemark(placemark: ET.Element) -> Feature:
    attributes: dict[str, Any] = {}
    name = _child(placemark, "name")
    if name is not None:
        attributes["name"] = (name.text or "").strip()
    extended = _child(placemark, "ExtendedData")
    if extended is not None:
        for data in extended.iter():
            if _local(data.tag) == "Data" and data.get("name"):
                value = _child(data, "value")
                attributes[data.get("name")] = (value.text or "") if value is not None else ""
            elif _local(data.tag) == "SimpleData" and data.get("name"):
                attributes[data.get("name")] = data.text or ""
    geometry = None
    for child in placemark:
        geometry = _geometry(child)
        if geometry is not None:
            break
    return (to_wkt(geometry) if geometry is not None else None, attributes)


def _coordinates(element: Optional[ET.Element]) -> list[tuple[float, float]]:
    coordinates = _child(element, "coordinates") if element is not None else None
    if coordinates is None or not (coordinates.text or "").strip():
        raise ValueError("KMLの形に座標(coordinates)がありません")
    points = []
    for item in coordinates.text.split():
        parts = item.split(",")
        try:
            points.append((float(parts[0]), float(parts[1])))
        except (IndexError, ValueError):
            raise ValueError(f"KMLの座標が読めません: {item}") from None
    return points


def _ring(boundary: ET.Element) -> list[tuple[float, float]]:
    return _coordinates(_child(boundary, "LinearRing"))


def _geometry(element: ET.Element) -> Optional[BaseGeometry]:
    """KMLの形の要素(Point・LineString・LinearRing・Polygon・MultiGeometry)。形でなければNone。"""
    kind = _local(element.tag)
    if kind == "Point":
        return shapely.Point(_coordinates(element)[0])
    if kind in ("LineString", "LinearRing"):
        return shapely.LineString(_coordinates(element))
    if kind == "Polygon":
        outer = _child(element, "outerBoundaryIs")
        if outer is None:
            raise ValueError("KMLの面に外周(outerBoundaryIs)がありません")
        holes = [_ring(inner) for inner in _children(element, "innerBoundaryIs")]
        return shapely.Polygon(_ring(outer), holes)
    if kind == "MultiGeometry":
        parts = [g for g in (_geometry(c) for c in element) if g is not None]
        kinds = {p.geom_type for p in parts}
        if kinds == {"Polygon"}:
            return shapely.MultiPolygon(parts)
        if kinds == {"LineString"}:
            return shapely.MultiLineString(parts)
        if kinds == {"Point"}:
            return shapely.MultiPoint(parts)
        return shapely.GeometryCollection(parts)
    return None
