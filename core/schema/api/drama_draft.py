# core/schema/api/drama_draft.py
"""
作品モデルの下書き(core.service.api.drama_draft)のDTO。下書きの中身はモデル定義YAMLの形
(DramaturgyDefinition)で返し、Apply・直接編集・取り込みは部分YAML(モデル定義YAMLの形で、変えたい部分だけ)を
リクエストの本文そのものとして受け取る(docs/database_design.md「部分YAMLの重ね合わせ」)。
"""

from typing import Optional

from pydantic import BaseModel


class DramaDraftCreateRequest(BaseModel):
    title: Optional[str] = None


class DramaDraftInfo(BaseModel):
    draft_id: str
    title: Optional[str] = None
    base_version: Optional[int] = None  # 元にした版(Noneは版が無い状態から)
    status: str  # open / confirmed / discarded
    created_at: str
    updated_at: str


class DramaDraftListResult(BaseModel):
    drafts: list[DramaDraftInfo]


class DramaDraftRevisionSummary(BaseModel):
    revision: int
    operation: str  # create / apply / edit / undo / import
    created_at: str


class DramaDraftRevisionListResult(BaseModel):
    revisions: list[DramaDraftRevisionSummary]


class DramaDraftChangeResult(BaseModel):
    """Apply・直接編集・取り込み・Undoの結果。revisionは積んだ履歴の番号。"""

    revision: int


class DramaDraftImportPathRequest(BaseModel):
    """サーバーの手元にあるモデル定義YAMLのファイルか、分割したファイルを置いたディレクトリを取り込む。"""

    path: str
    replace: bool = False


class DramaDraftConfirmRequest(BaseModel):
    note: Optional[str] = None


class DramaDraftConfirmResult(BaseModel):
    version: int  # 確定でできた版の番号
