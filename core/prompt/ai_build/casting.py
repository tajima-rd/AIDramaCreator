# core/prompt/ai_build/casting.py
"""
Build with AIの配役の工程(docs/architecture.md 9節・10節)。相談相手はCastingDirector。

- Casting(cast_character): この作品の人物に配役し、役の重さ(主役・脇役・端役)・演じ方・声の条件(性別・言語・訛り)を決める
- Audition(assign_voice): 配役ごとに、条件に合う音声合成の声(話者)を、提供元の声の一覧から選ぶ

生成AIは識別子を決めず、配役を人物の名前で指す(同じ人物の配役があれば更新、無ければ追加)。配役は削除させない
(削除は利用者がDramaturgy EditorのCastsタブで行う)。人物の設定は変えさせない。
"""

from typing import Optional

from pydantic import BaseModel, Field

from core.genai import VoiceInfo
from core.genai.prompt import BulletInstruction, ForbiddenRule, MandatoryRule, Prompt, Section
from core.infra.io.model_definition_reader import ModelDefinition
from core.model.agent import Actor
from core.model.agent.base_agent import BaseAgent
from core.model.drama import Cast, Dramaturgy
from core.prompt.agent_instruction import agent_task_sections
from core.prompt.ai_build.common import COMMON_RULES, BuildMode, EvidenceItem
from core.prompt.character_import import proposal_text
from core.prompt.drama_production.dialogue import character_profile

CASTING_TASK = "cast_character"
AUDITION_TASK = "assign_voice"

BILLING_LABELS = {"lead": "主役", "supporting": "脇役", "minor": "端役"}


class CastDraft(BaseModel):
    """配役(追加か更新)。分からない値・変えない値は空文字。"""

    character: str = Field(description="演じる人物の名前(この作品の登場人物・プロジェクトの人物の名前のまま)")
    billing: str = Field(description="役の重さ。lead(主役)・supporting(脇役)・minor(端役)のどれか。決めないなら空文字")
    performance_title: str = Field(description="演じ方の短い見出し(例: 頼れる案内役)。無ければ空文字")
    performance_description: str = Field(description="演じ方の説明(声の印象・話しぶり・感情の出し方)。無ければ空文字")
    pace: str = Field(description="話す速さ(例: 比較的ゆっくり)。無ければ空文字")
    voice_gender: str = Field(description="声を当てるときの性別。male・female・neutralのどれか。決めないなら空文字")
    language: str = Field(description="話す言語のコード(例: ja)。決めないなら空文字")
    accent: str = Field(description="訛り・話しぶり(例: 関西弁・標準語)。無ければ空文字")


class VoiceChoice(BaseModel):
    character: str = Field(description="配役の人物の名前")
    voice_id: str = Field(description="選んだ声の識別子(声の一覧のidをそのまま)")
    reason: str = Field(description="その声を選んだ理由(条件のどこに合うか)。短く")


class _Reply(BaseModel):
    message: str = Field(description="利用者への返事")
    has_proposal: bool = Field(description="追加・変更の提案があればtrue")
    evidence: list[EvidenceItem] = Field(description="根拠。無ければ空")
    questions: list[str] = Field(description="利用者への質問。無ければ空")
    warnings: list[str] = Field(description="利用者が確かめるとよい注意。無ければ空")


class CastingReply(_Reply):
    casts: list[CastDraft] = Field(description="追加・更新する配役。提案が無ければ空")


class AuditionReply(_Reply):
    auditions: list[VoiceChoice] = Field(description="配役ごとに選んだ声。提案が無ければ空")


GUIDE = {
    CASTING_TASK: [
        "配役は、作品の中で台詞を話す人物ごとに1つ。台詞の無い人物には配役を作らない。",
        "役の重さ(billing)は、物語の中心の人物をlead(主役)、それを支える人物をsupporting(脇役)、少しだけ話す人物(通行人等)をminor(端役)にする。",
        "演じ方(見出し・説明・話す速さ)と声の条件(性別・言語・訛り)は、次の工程(Audition)で声を選ぶ条件になる。人物の年齢・性別・人物像・話し方から決める。",
        "既存の配役は人物の名前で指す。提案には、追加する配役と変える配役だけを入れる。",
    ],
    AUDITION_TASK: [
        "配役ごとに、声の一覧から、役の重さ・演じ方・声の性別・言語・訛りの条件に最も合う声を1つ選ぶ。",
        "声の識別子(voice_id)は、声の一覧のidをそのまま書く。一覧に無い声を作らない。",
        "主役・脇役には、互いに聞き分けやすい、別の声を選ぶ。",
        "選んだ理由(reason)に、条件のどこに合うかを短く書く。",
    ],
}

PROHIBITIONS = [
    "人物の設定(名前・年齢・人物像等)を書き換えない。",
    "配役を削除しない(削除は利用者が行う)。",
    "識別子(id・key)を書かない(声の識別子voice_idは除く)。",
]

TITLES = {CASTING_TASK: "配役と演じ方を決める", AUDITION_TASK: "声を選ぶ(Audition)"}

ONE_SHOT_RULES = [
    "利用者の要望・企画書・人物の設定・今の配役から、この工程の内容を1回で作り、has_proposalをtrueにする。",
    "返事(message)には、作った内容の要点と、利用者が確かめるとよい点を短く書く。",
]

DIALOGUE_RULES = [
    "利用者と相談する。考えや選択肢を示し、利用者の判断を助ける。",
    "追加・変更の提案があるときだけhas_proposalをtrueにする。提案が無いときはfalseにし、提案の欄は空にする。",
    "利用者が求めていない配役を勝手に変えない。",
]

REPLIES: dict[str, type[_Reply]] = {CASTING_TASK: CastingReply, AUDITION_TASK: AuditionReply}


def casting_prompt(agent: Optional[BaseAgent], task_code: str, mode: BuildMode) -> Prompt:
    rules = COMMON_RULES + (ONE_SHOT_RULES if mode is BuildMode.ONE_SHOT else DIALOGUE_RULES)
    return Prompt(
        components=[
            *agent_task_sections(agent, task_code),
            Section(
                title=TITLES[task_code],
                children=[
                    BulletInstruction(items=GUIDE[task_code]),
                    MandatoryRule(BulletInstruction(items=rules)),
                    ForbiddenRule(BulletInstruction(items=PROHIBITIONS)),
                ],
            ),
        ]
    )


def cast_text(cast: Cast, actor: Optional[Actor] = None) -> str:
    """配役の1行(役の重さ・演じ方・声の条件と、選んである声)。"""
    performance = cast.performance
    facts = [
        BILLING_LABELS.get(cast.billing.value, cast.billing.value) if cast.billing else None,
        performance.title,
        performance.description,
        f"話す速さ: {performance.pace}" if performance.pace else None,
        f"声の性別: {cast.voice_gender.value}" if cast.voice_gender else None,
        f"言語: {cast.language}" if cast.language else None,
        f"訛り: {cast.accent}" if cast.accent else None,
        f"選んである声: {actor.voice_name}" if actor and actor.voice_name else None,
    ]
    return f"* {cast.character.name}: " + (" / ".join(f for f in facts if f) or "(条件はまだ無い)")


def _actor_of(dramaturgy: Dramaturgy, cast: Cast) -> Optional[Actor]:
    return next((a for a in dramaturgy.agents if isinstance(a, Actor) and a.casting_id == cast.id), None)


def casting_context(model: ModelDefinition, dramaturgy: Dramaturgy) -> str:
    """Castingの工程に渡す今の内容(企画書・登場人物の設定・今の配役)。"""
    lines = [proposal_text(dramaturgy.proposal), "", "# この作品の登場人物"]
    lines += [
        ("##" + character_profile(c)).replace("\n## ", "\n#### ") for c in dramaturgy.characters
    ] or ["(まだいない。Build with AIのCharactersの工程で作る)"]
    lines += ["", "# 今の配役"]
    lines += [cast_text(c) for c in dramaturgy.casts] or ["(まだ無い)"]
    return "\n".join(lines)


def voice_text(voice: VoiceInfo) -> str:
    facts = [voice.gender, f"声の高さ{voice.pitch}" if voice.pitch else None, voice.accent, voice.persona, voice.description]
    return f"* {voice.voice_id}: " + " / ".join(f for f in facts if f)


def audition_context(dramaturgy: Dramaturgy, voices: list[VoiceInfo], language: str) -> str:
    """Auditionの工程に渡す今の内容(配役とその条件・選んである声と、選べる声の一覧)。"""
    lines = ["# 配役(条件)"]
    lines += [cast_text(c, _actor_of(dramaturgy, c)) for c in dramaturgy.casts] or [
        "(まだ無い。Castingの工程で作る)"
    ]
    lines += ["", f"# 選べる声の一覧(言語: {language}。idが声の識別子)"]
    lines += [voice_text(v) for v in voices] or ["(この言語の声はありません)"]
    return "\n".join(lines)
