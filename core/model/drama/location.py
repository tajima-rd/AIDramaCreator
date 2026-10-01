# core/model/drama/location.py
"""場所。"""

from typing import Optional

from core.model.identifier import new_id


class Location:
    """劇中の場所。latitude・longitudeは緯度・経度。"""

    def __init__(
        self,
        name: str,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        address: Optional[str] = None,
        instruction: Optional[str] = None,
        description: Optional[str] = None,
    ):
        self.id: str = new_id()  # 識別子(不変)。nameは変更できる名前
        self.name: str = name
        self.latitude: Optional[float] = latitude
        self.longitude: Optional[float] = longitude
        self.address: Optional[str] = address
        self.instruction: Optional[str] = instruction
        self.description: Optional[str] = description
