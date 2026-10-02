# core/schema/api/ai_build.py
"""
Build with AI(core.service.api.ai_build)のDTO。会話は作品ごとに1本で、工程(タブ)ごとに分けて見せる・送る
(docs/architecture.md 10節)。提案は、工程の内容の形(Proposalなら企画書の全項目)で返す。
"""

from typing import Any, Literal, Optional

from pydantic import BaseModel


class AiBuildStepInfo(BaseModel):
    key: str
    label: str
    role_name: str  # 相談相手の職能(モデル定義YAMLの区画名の単数形)
    task_code: str
    available: bool  # Falseの工程はタブを並べるが選べない


class AiBuildStepListResult(BaseModel):
    steps: list[AiBuildStepInfo]


class AiBuildMessageInfo(BaseModel):
    id: int
    step: str
    role: Literal["user", "assistant"]
    mode: Optional[Literal["one_shot", "dialogue"]] = None
    text: str
    proposal: Optional[dict[str, Any]] = None  # 生成AIの提案(工程の内容の形)。提案が無ければNone
    changed_fields: list[str] = []  # 提案で変わる項目
    evidence: list[dict[str, str]] = []  # {target, source, quote}
    questions: list[str] = []
    warnings: list[str] = []
    proposal_status: Optional[Literal["pending", "applied", "undone"]] = None
    reference_file_ids: list[str] = []
    created_at: str


class AiBuildMessageListResult(BaseModel):
    messages: list[AiBuildMessageInfo]


class AiBuildSendRequest(BaseModel):
    draft_id: str  # 編集用の下書き(今の内容を読む)
    dramaturgy_id: str
    mode: Literal["one_shot", "dialogue"]
    text: str = ""  # ワンショット下書きでは空でもよい
    reference_file_ids: list[str] = []  # 参照する資料(Dataset)


class AiBuildProposalActionRequest(BaseModel):
    draft_id: str  # 反映・取り消しをする編集用の下書き


class AiBuildClearResult(BaseModel):
    deleted: int
