# core/prompt/ai_build/synopsis.py
"""
Build with AIのあらすじの工程(Synopsis。docs/architecture.md 10節)。相談相手はScriptwriter、タスクはwrite_synopsis。

作品全体のあらすじ(メタメタストーリー)と、幕ごとの題・あらすじ(メタストーリー)を書く。シーンのあらすじ(プロット)は扱わない。
生成AIは幕を番号(1から)で指し、今ある幕の題・あらすじだけを書く(幕の追加・削除はさせない。幕数は利用者がActsタブで決める)。
空の値では既存の値を消さない(対話でもワンショットでも)。
"""

from typing import Any, Optional

from pydantic import BaseModel, Field

from core.genai.prompt import BulletInstruction, ForbiddenRule, MandatoryRule, Prompt, Section
from core.model.agent.base_agent import BaseAgent
from core.model.drama import Act, Dramaturgy, Location, Scene
from core.prompt.agent_instruction import agent_task_sections
from core.prompt.ai_build.common import COMMON_RULES, BuildMode, EvidenceItem
from core.prompt.character_import import proposal_text
from core.prompt.drama_production.dialogue import character_profile

TASK = "write_synopsis"


class ActSynopsisDraft(BaseModel):
    """幕の題・あらすじ(更新)。変えない値は空文字。"""

    number: int = Field(description="幕の番号(今の幕の一覧の「第N幕」のN。1から)")
    title: str = Field(description="幕の題。変えないなら空文字")
    synopsis: str = Field(description="幕のあらすじ(メタストーリー)。変えないなら空文字")


class SynopsisReply(BaseModel):
    message: str = Field(description="利用者への返事")
    has_proposal: bool = Field(description="あらすじを変える提案があればtrue")
    synopsis: str = Field(description="作品全体のあらすじ。変えないなら空文字")
    acts: list[ActSynopsisDraft] = Field(description="題・あらすじを変える幕。提案が無ければ空")
    evidence: list[EvidenceItem] = Field(description="根拠。無ければ空")
    questions: list[str] = Field(description="利用者への質問。無ければ空")
    warnings: list[str] = Field(description="利用者が確かめるとよい注意。無ければ空")


GUIDE = [
    "作品全体のあらすじ(メタメタストーリー)は、物語の始まりから結末までの流れを、主な人物と場所を挙げて書く。",
    "幕のあらすじ(メタストーリー)は、その幕で起きること・人物の変化・次の幕へのつながりを書く。幕どうしで流れがつながるようにする。",
    "企画書(特に企画意図・あらすじ・対象地域)、この作品の登場人物と人物関係、作品で使う場所(案内すること・事実)を元にする。",
    "幕にシーンがあれば、そのシーンの題・場所・あらすじと食い違わないようにする。",
    "あらすじは、作品の入力の言語(無ければ利用者の言語)で書く。",
    "幕は「今の幕」の番号で指す。提案には、変える幕だけを入れる。",
]

ONE_SHOT_RULES = [
    "利用者の要望・資料・企画書・人物・今のあらすじから、作品全体のあらすじと、すべての幕の題・あらすじを1回で書き、has_proposalをtrueにする。",
    "今のあらすじに良いところがあれば活かす。",
    "返事(message)には、作った内容の要点と、利用者が確かめるとよい点を短く書く。",
]

DIALOGUE_RULES = [
    "利用者と相談する。考えや選択肢を示し、利用者の判断を助ける。",
    "変える提案があるときだけhas_proposalをtrueにする。提案が無いときはfalseにし、synopsisは空文字、actsは空にする。",
    "利用者が求めていない幕・項目を勝手に変えない。",
]

PROHIBITIONS = [
    "幕を増やしたり減らしたりしない(今の幕の一覧に無い番号を書かない。幕数は利用者が決める)。",
    "シーンのあらすじ・人物の設定を書き換えない。",
]


def synopsis_prompt(agent: Optional[BaseAgent], mode: BuildMode) -> Prompt:
    rules = COMMON_RULES + (ONE_SHOT_RULES if mode is BuildMode.ONE_SHOT else DIALOGUE_RULES)
    title = (
        "作品と幕のあらすじをワンショットで下書きする"
        if mode is BuildMode.ONE_SHOT
        else "作品と幕のあらすじについて利用者と相談する"
    )
    return Prompt(
        components=[
            *agent_task_sections(agent, TASK),
            Section(
                title=title,
                children=[
                    BulletInstruction(items=GUIDE),
                    MandatoryRule(BulletInstruction(items=rules)),
                    ForbiddenRule(BulletInstruction(items=PROHIBITIONS)),
                ],
            ),
        ]
    )


def ordered_acts(dramaturgy: Dramaturgy) -> list[Act]:
    """幕を並びの順に(n番目が「第n+1幕」)。"""
    return sorted(dramaturgy.acts, key=lambda a: a.order)


def ordered_scenes(act: Act) -> list[Scene]:
    """幕のシーンを並びの順に(n番目が「シーンn+1」)。"""
    return sorted(act.scenes, key=lambda s: s.order)


def _act_text(number: int, act: Act) -> list[str]:
    lines = [f"## 第{number}幕: {act.title or '(題なし)'}", act.synopsis or "(あらすじはまだ無い)"]
    for scene_number, scene in enumerate(ordered_scenes(act), start=1):
        facts = [scene.location.name if scene.location else None, scene.synopsis]
        lines.append(
            f"* シーン{scene_number}: {scene.title or '(題なし)'}"
            + "".join(f" / {f}" for f in facts if f)
        )
    return lines


def location_lines(location: Location, indent: str = "") -> list[str]:
    """場所の1項目(名前と、住所・その場所で案内すること・その場所の事実)。"""
    lines = [f"{indent}* {location.name}"]
    for label, value in (
        ("住所", location.address),
        ("この場所で案内すること", location.instruction),
        ("この場所の事実", location.description),
    ):
        if value:
            lines.append(f"{indent}  * {label}: {value}")
    return lines


def dramaturgy_background(dramaturgy: Dramaturgy) -> list[str]:
    """あらすじを書く元になる内容(企画書・登場人物・場所・作品の題・言語・作品全体のあらすじ)。"""
    lines = [proposal_text(dramaturgy.proposal), "", "# この作品の登場人物"]
    # 人物設定の見出し(#・##)を、この節の下の深さ(###・####)にする
    lines += [
        ("##" + character_profile(c)).replace("\n## ", "\n#### ") for c in dramaturgy.characters
    ] or ["(まだいない。Build with AIのCharactersの工程で作る)"]
    lines += ["", "# 作品で使う場所"]
    lines += [line for loc in dramaturgy.locations for line in location_lines(loc)] or ["(まだ無い)"]
    lines += ["", f"# 作品: {dramaturgy.title}"]
    if dramaturgy.input_language:
        lines.append(f"(作品の入力の言語: {dramaturgy.input_language})")
    lines += ["", "## 作品全体のあらすじ", dramaturgy.synopsis or "(まだ無い)"]
    return lines


def synopsis_context(dramaturgy: Dramaturgy) -> str:
    """生成AIに渡す今の内容(企画書・登場人物・場所・今の作品と幕のあらすじ、幕のシーン)。"""
    lines = dramaturgy_background(dramaturgy)
    lines += ["", "# 今の幕"]
    acts = ordered_acts(dramaturgy)
    for number, act in enumerate(acts, start=1):
        lines += _act_text(number, act)
    if not acts:
        lines.append("(幕が無い。幕はDramaturgy EditorのActsタブで足す)")
    return "\n".join(lines)


def synopsis_summary(proposal: dict[str, Any]) -> str:
    """生成AIの過去の提案(画面に出す提案の対応表)を、会話の履歴に入れるための文。"""
    lines = []
    if (proposal.get("synopsis") or "").strip():
        lines += ["## 作品全体のあらすじ", proposal["synopsis"].strip()]
    for act in proposal.get("acts") or []:
        lines.append(f"## 第{act.get('number')}幕: {(act.get('title') or '').strip() or '(題は変えない)'}")
        if (act.get("synopsis") or "").strip():
            lines.append(act["synopsis"].strip())
    return "\n".join(lines)
