# core/schema/api/character_import.py
"""
企画書の登場人物の取り込み(core.service.api.character_import)のDTO。登場人物は名前で特定する
(企画書の登場人物とプロジェクトの人物は、名前が同じなら同じ人物とみなす。docs/architecture.md 9節)。
"""

from typing import Literal

from pydantic import BaseModel


class CharacterConflictCheckRequest(BaseModel):
    dramaturgy_id: str  # 企画書を持つ作品
    name: str  # 企画書の登場人物の名前(登録済みの人物と同じ名前)


class CharacterConflictCheckResult(BaseModel):
    character_id: str  # 登録済みの人物
    conflict: bool
    reasons: list[str]  # 矛盾の理由(当面は保存しない)


class CharacterImportRequest(BaseModel):
    dramaturgy_id: str
    name: str
    mode: Literal["create", "merge", "replace"]  # 未登録なら create、登録済みなら merge か replace


class CharacterImportResult(BaseModel):
    revision: int  # 下書きの履歴の番号
    character_id: str  # 作った・更新した人物
