# core/model/drama/script.py
"""
台詞の段階(Scriptwriterが書く)。演出付きの原稿(ScriptElement)とは分離する。
"""

from typing import Optional

from core.model.drama.cast import Cast
from core.model.identifier import new_id


class Line:
    """台詞の1行。castは話者。"""

    def __init__(self, order: int, cast: Cast, text: str):
        self.id: str = new_id()  # 識別子(不変)
        self.order: int = order
        self.cast: Cast = cast
        self.text: str = text


class Script:
    """1つのSceneの台詞。"""

    def __init__(self, lines: Optional[list[Line]] = None):
        self.lines: list[Line] = list(lines or [])
