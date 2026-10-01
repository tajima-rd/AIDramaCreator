# core/model/drama/proposal.py
"""
企画書。作品制作の初期シード(2026-10-01ユーザー決定)。企画段階では仮の設定が多いため、題・あらすじ・登場人物も
作品(Dramaturgy)とは共有せず、企画書が自分で持つ。Dramaturgy.synopsisは作品を確定する段階で作るもので、企画書のあらすじとは別。
企画書の内容は後から修正できる(すべて省略できる)。
"""

from typing import Optional


class ProposalCharacter:
    """企画書の登場人物(仮の設定)。正式な人物(Character)とは別で、名前と説明だけを持つ。"""

    def __init__(self, name: Optional[str] = None, description: Optional[str] = None):
        self.name: Optional[str] = name
        self.description: Optional[str] = description


class Proposal:
    """catchphrase=キャッチコピー、logline=ログライン、intent=企画意図、target_area=対象地域(文字列。暫定)、
    synopsis=企画書のあらすじ、characters=登場人物(仮の設定)。"""

    def __init__(
        self,
        title: Optional[str] = None,
        catchphrase: Optional[str] = None,
        logline: Optional[str] = None,
        intent: Optional[str] = None,
        target_area: Optional[str] = None,
        synopsis: Optional[str] = None,
        characters: Optional[list[ProposalCharacter]] = None,
    ):
        self.title: Optional[str] = title
        self.catchphrase: Optional[str] = catchphrase
        self.logline: Optional[str] = logline
        self.intent: Optional[str] = intent
        self.target_area: Optional[str] = target_area
        self.synopsis: Optional[str] = synopsis
        self.characters: list[ProposalCharacter] = list(characters or [])
