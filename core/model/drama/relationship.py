# core/model/drama/relationship.py
"""
人物関係。向きを持つ(sourceから見たtarget)。同じ2人の関係が時期によって変わるため、時期(TemporalNode)を持てる。
人物の側からも引ける(Character.relationships。sourceとtargetの両方の人物に加わる)。
"""

from typing import TYPE_CHECKING, Optional

from core.model.drama.temporal import TemporalNode
from core.model.identifier import new_id

if TYPE_CHECKING:
    from core.model.drama.character import Character


class Relationship:
    """sourceから見たtargetとの関係。labelは短い名前(例: 幼馴染)。"""

    def __init__(
        self,
        source: "Character",
        target: "Character",
        label: str,
        period: Optional[TemporalNode] = None,
        description: Optional[str] = None,
    ):
        self.id: str = new_id()  # 識別子(不変)
        self.source: Character = source
        self.target: Character = target
        self.label: str = label
        self.period: Optional[TemporalNode] = period
        self.description: Optional[str] = description
        # 関連の人物の側(Character.relationships)をそろえる
        source.relationships.append(self)
        if target is not source:
            target.relationships.append(self)
