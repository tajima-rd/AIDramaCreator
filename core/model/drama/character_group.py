# core/model/drama/character_group.py
"""
人物のまとまり(家族・職場・仲間等)。人物と同じく作品が所有せず(持ち主はProject)、人物を参照で持つ(2026-10-01ユーザー決定)。
"""

from typing import Optional

from core.model.drama.character import Character
from core.model.identifier import new_id


class CharacterGroup:
    """nameはまとまりの名前(例: 加藤家)、kindは種類(自由に書く。例: 家族・職場)、membersは属する人物(参照)、
    descriptionは説明。"""

    def __init__(
        self,
        name: str,
        kind: Optional[str] = None,
        members: Optional[list[Character]] = None,
        description: Optional[str] = None,
    ):
        self.id: str = new_id()  # 識別子(不変)。nameは変更できる名前
        self.name: str = name
        self.kind: Optional[str] = kind
        self.members: list[Character] = list(members or [])  # 参照
        self.description: Optional[str] = description
