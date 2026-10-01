# core/schema/api/drama_model.py
"""
作品モデルの正本と版(core.service.api.drama_model)のDTO。作品の中身は、モデル定義YAMLの形
(core.schema.formats.dramaturgy_definition.DramaturgyDefinition)で返す(docs/architecture.md 7節)。
"""

from typing import Optional

from pydantic import BaseModel


class DramaModelVersionSummary(BaseModel):
    version: int
    created_at: str
    draft_id: Optional[str] = None
    note: Optional[str] = None


class DramaModelVersionListResult(BaseModel):
    current_version: Optional[int] = None
    versions: list[DramaModelVersionSummary]
