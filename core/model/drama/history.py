# core/model/drama/history.py
"""作品の時間の位相を束ねる。"""

from typing import Optional

from core.model.drama.temporal import TemporalEdge


class History:
    """TemporalEdgeの集まり。"""

    def __init__(self, edges: Optional[list[TemporalEdge]] = None):
        self.edges: list[TemporalEdge] = list(edges or [])
