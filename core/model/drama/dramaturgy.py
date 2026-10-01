# core/model/drama/dramaturgy.py
"""
作品全体を包括するドラマツルギー(QIDMのDomainに相当する階層。集約の根はProject)。
階層は Dramaturgy → Act → Scene で、各階層があらすじを持つ(synopsisは作品全体のメタメタストーリー)。
翻訳はSceneの段階と音声の生成の間で、input_languageからoutput_languageへ行う。
"""

from typing import Optional

from core.model.drama.act import Act
from core.model.drama.cast import Cast
from core.model.drama.character import Character
from core.model.drama.history import History
from core.model.drama.premise import Premise
from core.model.identifier import new_id


class Dramaturgy:
    """1つの作品。言語はBCP 47等のコード(例: ja・zh)を想定。"""

    def __init__(
        self,
        title: str,
        synopsis: Optional[str] = None,
        input_language: Optional[str] = None,
        output_language: Optional[str] = None,
        premise: Optional[Premise] = None,
        characters: Optional[list[Character]] = None,
        casts: Optional[list[Cast]] = None,
        acts: Optional[list[Act]] = None,
        history: Optional[History] = None,
    ):
        self.id: str = new_id()  # 識別子(不変)。titleは変更できる題
        self.title: str = title
        self.synopsis: Optional[str] = synopsis
        self.input_language: Optional[str] = input_language
        self.output_language: Optional[str] = output_language
        self.premise: Premise = premise if premise is not None else Premise()
        self.characters: list[Character] = list(characters or [])
        self.casts: list[Cast] = list(casts or [])
        self.acts: list[Act] = list(acts or [])
        self.history: History = history if history is not None else History()
