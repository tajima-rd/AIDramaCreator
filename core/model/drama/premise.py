# core/model/drama/premise.py
"""
前提の知識。地域課題・方針・観光戦略等。何も与えなくてもよい。
"""

from typing import Optional


class Premise:
    """textは前提の本文。"""

    def __init__(self, text: Optional[str] = None):
        self.text: Optional[str] = text
