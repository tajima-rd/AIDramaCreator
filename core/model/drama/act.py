# core/model/drama/act.py
"""幕。synopsisは幕のメタストーリー。"""

from typing import Optional

from core.model.drama.scene import Scene
from core.model.identifier import new_id


class Act:
    """Dramaturgyの中の幕。"""

    def __init__(
        self,
        order: int,
        title: Optional[str] = None,
        synopsis: Optional[str] = None,
        scenes: Optional[list[Scene]] = None,
    ):
        self.id: str = new_id()  # 識別子(不変)
        self.order: int = order
        self.title: Optional[str] = title
        self.synopsis: Optional[str] = synopsis
        self.scenes: list[Scene] = list(scenes or [])
