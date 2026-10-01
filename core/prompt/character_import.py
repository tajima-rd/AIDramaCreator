# core/prompt/character_import.py
"""
企画書の登場人物の取り込み(core.service.process.genai.character_importer)のプロンプトと、生成AIに返させる構造。
担うのはScriptwriterのタスク(import_proposal_character・check_character_conflict。docs/architecture.md 9節)。

- 骨組み(sketch): 企画書の登場人物の説明と企画書全体から、人物の骨組みを作る(まだ登録されていない人物・置き換え)
- 統合(merge): 登録済みの人物の設定と、企画書の説明を合わせた設定を作る
- 矛盾の確認(conflict): 登録済みの人物の設定と、企画書の説明が両立するかを確かめる

設定の少ない人物は不備ではない(docs/overview.md「世界観が先、作品は後」)ので、詳しさの違いを矛盾として扱わせない。
経歴・人物関係は時期と相手が要るので、骨組みには含めない。
"""

from typing import Optional

from pydantic import BaseModel, Field

from core.genai.prompt import BulletInstruction, ForbiddenRule, MandatoryRule, Prompt, PromptComponent, Section, TextBlock
from core.model.agent.base_agent import BaseAgent
from core.model.drama import Character
from core.model.drama.proposal import Proposal, ProposalCharacter
from core.prompt.agent_instruction import agent_task_sections
from core.prompt.drama_production.dialogue import character_profile

IMPORT_TASK = "import_proposal_character"
CONFLICT_TASK = "check_character_conflict"

# 構造化出力は提供元(手元のllama.cpp等)によって省略可能な項目の扱いが違うため、すべての項目を必須にし、
# 分からない値は空文字で返させる(空文字は処理の側で未設定にする)


class FeatureSketch(BaseModel):
    item: str = Field(description="項目の名前(例: 職業)")
    value: str = Field(description="項目の値。分からなければ空文字")
    definition: str = Field(description="項目の名前の意味。一般的な言葉なら空文字")
    description: str = Field(description="補足。無ければ空文字")


class CharacteristicSketch(BaseModel):
    item: str = Field(description="特徴のまとまりの名前(例: 人物像・外見・物語での役割)")
    definition: str = Field(description="まとまりの名前の意味。一般的な言葉なら空文字")
    description: str = Field(description="まとまりの説明文。無ければ空文字")
    features: list[FeatureSketch]


class CharacterSketch(BaseModel):
    """人物の骨組み(名前は企画書のまま変えないので返させない)。"""

    reading: str = Field(description="名前の読み(かな)。分からなければ空文字")
    gender: str = Field(description="性別。分からなければ空文字")
    age: str = Field(description="年齢・年代(例: 40代)。分からなければ空文字")
    first_person: str = Field(description="一人称。分からなければ空文字")
    tone: str = Field(description="相手を問わない既定の口調。分からなければ空文字")
    speech_description: str = Field(description="話し方の説明。無ければ空文字")
    characteristics: list[CharacteristicSketch]


class CharacterConflictResponse(BaseModel):
    conflict: bool = Field(description="両立しない点が1つでもあればtrue")
    reasons: list[str] = Field(description="両立しない点。1つにつき1文で、どちらに何と書かれているかを示す。無ければ空")


COMMON_RULES = [
    "企画書と同じ言語で書く。",
    "名前は企画書のまま使い、変えない。",
]

SKETCH_INSTRUCTIONS = [
    "企画書の登場人物1人について、人物の骨組みを作る。",
    "根拠は、その人物の説明と企画書全体(題・ログライン・企画意図・対象地域・あらすじ・ほかの登場人物)。",
    "説明に書かれていないことは、企画書全体から自然に推せる範囲で補う。推せないことは空文字にする。",
    "骨組みなので、細部を作り込みすぎない。設定が少ないことは不備ではない。",
    "人物の説明に書かれた内容は、人物像の特徴(characteristics)のどこかに必ず残す。",
]

MERGE_INSTRUCTIONS = [
    "登録済みの人物の設定と、新しい企画書でのその人物の説明を合わせた設定を作る。",
    "登録済みの設定を土台にし、企画書の説明で新しく分かったことを足す。食い違うところは、企画書の説明を優先する。",
    "登録済みの特徴(characteristics)は、変える必要の無いものをそのまま残す。返した特徴の一覧で、登録済みの一覧を置き換える。",
    "登録済みの値を消さない。分からない値は、登録済みの値をそのまま返す。",
]

CONFLICT_INSTRUCTIONS = [
    "登録済みの人物の設定と、新しい企画書でのその人物の説明が、同じ人物として両立するかを確かめる。",
    "両立しない点(年齢・性別・職業・家族・出来事等の事実の食い違い)だけを挙げる。",
    "一方にだけ書かれていること、詳しさの違いは矛盾ではない。設定の少ない人物に新しい設定が付くのは自然なことである。",
]

SKETCH_PROHIBITIONS = [
    "経歴・人物関係を作らない(時期と相手が要るため、別の作業で作る)。",
    "企画書に無い固有名詞(地名・団体名・ほかの人物の名前)を作らない。",
]


def _prompt(agent: Optional[BaseAgent], task_code: str, title: str, instructions: list[str], prohibitions: list[str]) -> Prompt:
    children: list[PromptComponent] = [
        BulletInstruction(items=instructions),
        MandatoryRule(BulletInstruction(items=COMMON_RULES)),
    ]
    if prohibitions:
        children.append(ForbiddenRule(BulletInstruction(items=prohibitions)))
    return Prompt(components=[*agent_task_sections(agent, task_code), Section(title=title, children=children)])


def sketch_prompt(agent: Optional[BaseAgent]) -> Prompt:
    return _prompt(agent, IMPORT_TASK, "人物の骨組みを作る", SKETCH_INSTRUCTIONS, SKETCH_PROHIBITIONS)


def merge_prompt(agent: Optional[BaseAgent]) -> Prompt:
    return _prompt(agent, IMPORT_TASK, "登録済みの人物と企画書の説明を統合する", MERGE_INSTRUCTIONS, SKETCH_PROHIBITIONS)


def conflict_prompt(agent: Optional[BaseAgent]) -> Prompt:
    return _prompt(agent, CONFLICT_TASK, "人物の設定の矛盾を確かめる", CONFLICT_INSTRUCTIONS, [])


def proposal_text(proposal: Proposal) -> str:
    """企画書をMarkdownにする。"""
    lines = ["# 企画書"]
    for label, value in (
        ("題", proposal.title),
        ("キャッチコピー", proposal.catchphrase),
        ("ログライン", proposal.logline),
        ("企画意図", proposal.intent),
        ("対象地域", proposal.target_area),
        ("あらすじ", proposal.synopsis),
    ):
        if value:
            lines += ["", f"## {label}", value]
    if proposal.characters:
        lines += ["", "## 登場人物"]
        lines += [f"* {c.name or '(名前なし)'}: {c.description or ''}" for c in proposal.characters]
    return "\n".join(lines)


def _target_text(target: ProposalCharacter) -> str:
    return f"# 対象の登場人物(企画書の説明)\n* 名前: {target.name}\n* 説明: {target.description or '(説明なし)'}"


def sketch_request(proposal: Proposal, target: ProposalCharacter) -> str:
    return f"{proposal_text(proposal)}\n\n{_target_text(target)}"


def merge_request(proposal: Proposal, target: ProposalCharacter, registered: Character) -> str:
    return (
        f"{proposal_text(proposal)}\n\n{_target_text(target)}\n\n"
        f"# 登録済みの人物の設定\n{character_profile(registered)}"
    )


def conflict_request(proposal: Proposal, target: ProposalCharacter, registered: Character) -> str:
    return merge_request(proposal, target, registered)
