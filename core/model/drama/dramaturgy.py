# core/model/drama/dramaturgy.py
"""
作品全体を包括するドラマツルギー(QIDMのDomainに相当する階層。集約の根はProject)。
階層は Dramaturgy → Act → Scene で、各階層があらすじを持つ(synopsisは作品全体のメタメタストーリー)。
翻訳はSceneの段階と音声の生成の間で、input_languageからoutput_languageへ行う。
人物(Character)と人物関係(Relationship)は作品が所有せず(持ち主はProject。作品をまたいで共有できる)、作品はこの作品に
関わるものを参照で持つ(2026-10-01ユーザー決定)。
作品作りに参加するエージェント(core.model.agent)は作品が所有する(作品ごとに役割・厳守事項等を書き換えられる。2026-10-01ユーザー決定)。
"""

from typing import Optional

from core.model.agent.base_agent import BaseAgent
from core.model.drama.act import Act
from core.model.drama.cast import Cast
from core.model.drama.character import Character
from core.model.drama.history import History
from core.model.drama.premise import Premise
from core.model.drama.proposal import Proposal
from core.model.drama.relationship import Relationship
from core.model.identifier import new_id


class Dramaturgy:
    """1つの作品。言語はBCP 47等のコード(例: ja・zh)を想定。characters・relationshipsは、この作品に関わる人物・人物関係への
    参照(所有しない)。premise・casts・acts・history・proposal(企画書)・agents(エージェント)は作品が所有する。"""

    def __init__(
        self,
        title: str,
        synopsis: Optional[str] = None,
        input_language: Optional[str] = None,
        output_language: Optional[str] = None,
        premise: Optional[Premise] = None,
        characters: Optional[list[Character]] = None,
        relationships: Optional[list[Relationship]] = None,
        casts: Optional[list[Cast]] = None,
        acts: Optional[list[Act]] = None,
        history: Optional[History] = None,
        proposal: Optional[Proposal] = None,
        agents: Optional[list[BaseAgent]] = None,
    ):
        self.id: str = new_id()  # 識別子(不変)。titleは変更できる題
        self.title: str = title
        self.synopsis: Optional[str] = synopsis
        self.input_language: Optional[str] = input_language
        self.output_language: Optional[str] = output_language
        self.premise: Premise = premise if premise is not None else Premise()
        self.characters: list[Character] = list(characters or [])  # 参照
        self.relationships: list[Relationship] = list(relationships or [])  # 参照
        self.casts: list[Cast] = list(casts or [])
        self.acts: list[Act] = list(acts or [])
        self.history: History = history if history is not None else History()
        self.proposal: Proposal = proposal if proposal is not None else Proposal()
        self.agents: list[BaseAgent] = list(agents or [])
