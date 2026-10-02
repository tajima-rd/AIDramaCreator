# core/gis/analysis/containment.py
"""点を含む面(包含)。境界の上も含むとみなす。"""

from typing import Any

import shapely
from shapely.geometry.base import BaseGeometry

from ..geometry import is_areal


def covers_point(area: BaseGeometry, point: tuple[float, float]) -> bool:
    """面areaが点pointを含むか(境界の上も含む)。面でなければFalse。"""
    return is_areal(area) and area.covers(shapely.Point(point))


def areas_covering(point: tuple[float, float], areas: list[tuple[Any, BaseGeometry]]) -> list[Any]:
    """areas((鍵, 形)の並び)のうち、点pointを含む面の鍵(並びの順)。"""
    return [key for key, area in areas if covers_point(area, point)]


def line_endpoints(line: BaseGeometry) -> tuple[tuple[float, float], tuple[float, float]]:
    """線の始点と終点。"""
    coords = list(line.coords)
    return coords[0], coords[-1]
