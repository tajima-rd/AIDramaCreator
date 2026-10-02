# core/model/drama/location.py
"""
場所。形(geometry)はWKTの文字列で持つ(座標はWGS84=EPSG:4326、経度・緯度の順。2026-10-02ユーザー決定)。
位置連動の音声(Locatone等)では、シーンの場所は面で、再生エリアに当たる。持ち主はProjectで、作品は使うものを参照で持つ。
"""

from typing import Optional

from core.model.identifier import new_id


class Location:
    """劇中の場所。geometryは形(WKT。例: POLYGON ((134.55 35.40, …)))。instructionはその場所で案内すること、
    descriptionはその場所の事実。"""

    def __init__(
        self,
        name: str,
        geometry: Optional[str] = None,
        address: Optional[str] = None,
        instruction: Optional[str] = None,
        description: Optional[str] = None,
    ):
        self.id: str = new_id()  # 識別子(不変)。nameは変更できる名前
        self.name: str = name
        self.geometry: Optional[str] = geometry
        self.address: Optional[str] = address
        self.instruction: Optional[str] = instruction
        self.description: Optional[str] = description
