# core/model/drama/site_flow.py
"""
SiteFlow: 場所(Location)どうしの移動(2026-10-02ユーザー決定)。地図の上では線で描き、線の始点を含むLocationがorigin、
終点を含むLocationがdestination。directionは線を引いた向き(origin→destination)に対する移動の向き。
Locationと同じく持ち主はProjectで、作品は使うものを参照で持つ。
"""

from enum import StrEnum
from typing import Optional

from core.model.drama.location import Location
from core.model.identifier import new_id


class SiteFlowDirection(StrEnum):
    """移動の向き(線を引いた向きに対して)。"""

    FORWARD = "forward"  # origin→destination
    BACKWARD = "backward"  # destination→origin
    BOTH = "both"  # 双方向


class SiteFlow:
    """originからdestinationへの移動。geometryは道筋の線(WKTのLINESTRING)。directionは未設定(None)でもよい。"""

    def __init__(
        self,
        origin: Location,
        destination: Location,
        direction: Optional[SiteFlowDirection] = None,
        geometry: Optional[str] = None,
        name: Optional[str] = None,
    ):
        self.id: str = new_id()  # 識別子(不変)
        self.origin: Location = origin  # 参照
        self.destination: Location = destination  # 参照
        self.direction: Optional[SiteFlowDirection] = direction
        self.geometry: Optional[str] = geometry
        self.name: Optional[str] = name
