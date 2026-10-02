# core/prompt/ai_build/proposal.py
"""
Build with AIのProposal(企画書)の工程。相談相手はScriptwriter、タスクはdraft_proposal。
企画書は作品制作の初期シードで、仮の設定でよい(docs/model_design.md)。
"""

from typing import Optional

from pydantic import BaseModel, Field

from core.genai.prompt import BulletInstruction, MandatoryRule, Prompt, Section
from core.model.agent.base_agent import BaseAgent
from core.model.drama.proposal import Proposal, ProposalCharacter
from core.prompt.agent_instruction import agent_task_sections
from core.prompt.ai_build.common import (
    COMMON_RULES,
    DIALOGUE_RULES,
    ONE_SHOT_RULES,
    BuildMode,
    EvidenceItem,
)
from core.prompt.character_import import proposal_text

TASK = "draft_proposal"


class ProposalCharacterDraft(BaseModel):
    name: str = Field(description="登場人物の名前(仮でよい)")
    description: str = Field(description="登場人物の説明(役割・人物像を1〜2文で)")


class ProposalDraft(BaseModel):
    """企画書の全項目(決まっていない項目は空文字)。"""

    title: str = Field(description="企画の仮の題")
    catchphrase: str = Field(description="キャッチコピー(1文)")
    logline: str = Field(description="ログライン(作品を数行で言い表す)")
    intent: str = Field(description="企画意図(なぜ作るか・地域の課題・対象とする人)")
    target_area: str = Field(description="対象地域")
    synopsis: str = Field(description="企画書のあらすじ")
    characters: list[ProposalCharacterDraft] = Field(description="登場人物(仮の設定)")


class ProposalReply(BaseModel):
    message: str = Field(description="利用者への返事")
    has_proposal: bool = Field(description="企画書を変える提案があればtrue")
    proposal: ProposalDraft = Field(
        description="提案した後の企画書の全体。提案が無ければ今の企画書のまま"
    )
    evidence: list[EvidenceItem] = Field(description="根拠。無ければ空")
    questions: list[str] = Field(description="利用者への質問。無ければ空")
    warnings: list[str] = Field(description="利用者が確かめるとよい注意。無ければ空")


PROPOSAL_GUIDE = [
    "企画書は、音声ドラマの制作を始めるための初期シード(仮の設定でよい)。項目は、題・キャッチコピー・ログライン・企画意図・"
    "対象地域・あらすじ・登場人物(名前と説明)。",
    "企画書の題・あらすじ・登場人物は、作品の正式な題・あらすじ・人物とは別に持つ(後で作品を作るときの元になる)。",
    "企画書は、作品の入力の言語(無ければ利用者の言語)で書く。",
]


def proposal_prompt(agent: Optional[BaseAgent], mode: BuildMode) -> Prompt:
    rules = COMMON_RULES + (ONE_SHOT_RULES if mode is BuildMode.ONE_SHOT else DIALOGUE_RULES)
    title = (
        "企画書をワンショットで下書きする"
        if mode is BuildMode.ONE_SHOT
        else "企画書について利用者と相談する"
    )
    return Prompt(
        components=[
            *agent_task_sections(agent, TASK),
            Section(
                title=title,
                children=[
                    BulletInstruction(items=PROPOSAL_GUIDE),
                    MandatoryRule(BulletInstruction(items=rules)),
                ],
            ),
        ]
    )


def proposal_context(proposal: Proposal, input_language: Optional[str]) -> str:
    """生成AIに渡す今の企画書(最新の利用者の発言に添える)。"""
    lines = [proposal_text(proposal)]
    if input_language:
        lines.append(f"(作品の入力の言語: {input_language})")
    return "\n".join(lines)


def proposal_summary(draft: ProposalDraft) -> str:
    """生成AIの過去の提案を、会話の履歴に入れるための文。"""
    return proposal_text(proposal_from_draft(draft))


def _blank(value: str) -> Optional[str]:
    value = (value or "").strip()
    return value or None


def proposal_from_draft(draft: ProposalDraft) -> Proposal:
    """生成AIの企画書(空文字は未設定)を、モデルの企画書にする。"""
    return Proposal(
        _blank(draft.title),
        _blank(draft.catchphrase),
        _blank(draft.logline),
        _blank(draft.intent),
        _blank(draft.target_area),
        _blank(draft.synopsis),
        [ProposalCharacter(_blank(c.name), _blank(c.description)) for c in draft.characters],
    )
