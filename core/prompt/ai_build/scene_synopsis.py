# core/prompt/ai_build/scene_synopsis.py
"""
Build with AIのシーンのあらすじの工程(Scenes。docs/architecture.md 10節)。相談相手はScriptwriter、タスクはwrite_synopsis。

シーンごとの題・あらすじ(プロット)を書く。場所・描く時期・状況は変えさせない(参考として渡す)。
生成AIはシーンを「第N幕のシーンM」(どちらも1から)で指し、今あるシーンだけを書く(シーンの追加・削除はさせない。
シーンは利用者がDramaturgy EditorのScenesタブ・Generate Scenesで作る)。空の値では既存の値を消さない(対話でもワンショットでも)。
"""

from typing import Any, Optional

from pydantic import BaseModel, Field

from core.genai.prompt import BulletInstruction, ForbiddenRule, MandatoryRule, Prompt, Section
from core.model.agent.base_agent import BaseAgent
from core.model.drama import Act, Dramaturgy, Scene
from core.prompt.ai_build.common import COMMON_RULES, BuildMode, EvidenceItem
from core.prompt.ai_build.synopsis import dramaturgy_background, location_lines, ordered_acts, ordered_scenes
from core.prompt.agent_instruction import agent_task_sections

TASK = "write_synopsis"


class SceneSynopsisDraft(BaseModel):
    """シーンの題・あらすじ(更新)。変えない値は空文字。"""

    act: int = Field(description="幕の番号(今のシーンの一覧の「第N幕」のN。1から)")
    scene: int = Field(description="その幕の中のシーンの番号(「シーンM」のM。1から)")
    title: str = Field(description="シーンの題。変えないなら空文字")
    synopsis: str = Field(description="シーンのあらすじ。変えないなら空文字")


class SceneSynopsisReply(BaseModel):
    message: str = Field(description="利用者への返事")
    has_proposal: bool = Field(description="シーンのあらすじを変える提案があればtrue")
    scenes: list[SceneSynopsisDraft] = Field(description="題・あらすじを変えるシーン。提案が無ければ空")
    evidence: list[EvidenceItem] = Field(description="根拠。無ければ空")
    questions: list[str] = Field(description="利用者への質問。無ければ空")
    warnings: list[str] = Field(description="利用者が確かめるとよい注意。無ければ空")


GUIDE = [
    "シーンのあらすじは、そのシーンで誰が何をし、何が起き、次のシーンへどうつながるかを書く。台詞はまだ書かない。",
    "作品全体のあらすじと幕のあらすじに沿わせ、幕の中のシーンどうしで流れがつながるようにする。",
    "シーンの場所・描く時期・状況が決まっていれば、それに合わせる。",
    "シーンの場所に「この場所で案内すること」があれば、そのシーンの中で人物が聞き手に案内する内容として、あらすじに入れる。"
    "「この場所の事実」は、案内や描写の裏付けに使い、事実と食い違う内容を書かない。",
    "企画書、この作品の登場人物と人物関係を元にする。",
    "あらすじは、作品の入力の言語(無ければ利用者の言語)で書く。",
    "シーンは「今のシーン」の幕とシーンの番号で指す。提案には、変えるシーンだけを入れる。",
]

ONE_SHOT_RULES = [
    "利用者の要望・資料・企画書・人物・作品と幕のあらすじ・今のシーンから、すべてのシーンの題・あらすじを1回で書き、has_proposalをtrueにする。",
    "今のシーンの題・あらすじに良いところがあれば活かす。",
    "返事(message)には、作った内容の要点と、利用者が確かめるとよい点を短く書く。",
]

DIALOGUE_RULES = [
    "利用者と相談する。考えや選択肢を示し、利用者の判断を助ける。",
    "変える提案があるときだけhas_proposalをtrueにする。提案が無いときはfalseにし、scenesは空にする。",
    "利用者が求めていないシーン・項目を勝手に変えない。",
]

PROHIBITIONS = [
    "シーンを増やしたり減らしたりしない(今のシーンの一覧に無い番号を書かない。シーンは利用者が作る)。",
    "シーンの場所・描く時期・状況、作品と幕のあらすじ、人物の設定を書き換えない。",
]


def scene_synopsis_prompt(agent: Optional[BaseAgent], mode: BuildMode) -> Prompt:
    rules = COMMON_RULES + (ONE_SHOT_RULES if mode is BuildMode.ONE_SHOT else DIALOGUE_RULES)
    title = (
        "シーンのあらすじをワンショットで下書きする"
        if mode is BuildMode.ONE_SHOT
        else "シーンのあらすじについて利用者と相談する"
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


def scene_text(number: int, scene: Scene) -> list[str]:
    """シーンの見出し・場所・時期・状況・あらすじ(Script・Scenesの工程で使う)。"""
    lines = [f"### シーン{number}: {scene.title or '(題なし)'}"]
    if scene.location:
        lines.append("* 場所:")
        lines += location_lines(scene.location, indent="  ")
    situation = scene.situation
    for label, value in (
        ("描く時期", (scene.period.label or scene.period.string_date) if scene.period else None),
        ("状況", situation.description),
        ("時間帯", situation.time_of_day),
        ("天候・環境", situation.environment),
    ):
        if value:
            lines.append(f"* {label}: {value}")
    lines.append(scene.synopsis or "(あらすじはまだ無い)")
    return lines


def _act_text(number: int, act: Act) -> list[str]:
    lines = ["", f"## 第{number}幕: {act.title or '(題なし)'}", f"幕のあらすじ: {act.synopsis or '(まだ無い)'}"]
    scenes = ordered_scenes(act)
    for scene_number, scene in enumerate(scenes, start=1):
        lines += scene_text(scene_number, scene)
    if not scenes:
        lines.append("(この幕にはシーンが無い)")
    return lines


def scene_synopsis_context(dramaturgy: Dramaturgy) -> str:
    """生成AIに渡す今の内容(企画書・登場人物・場所・作品のあらすじと、幕ごとのあらすじ・シーン)。"""
    lines = dramaturgy_background(dramaturgy)
    lines += ["", "# 今のシーン"]
    acts = ordered_acts(dramaturgy)
    for number, act in enumerate(acts, start=1):
        lines += _act_text(number, act)
    if not any(act.scenes for act in acts):
        lines.append("(シーンが無い。シーンはDramaturgy EditorのScenesタブかGenerate Scenesで作る)")
    return "\n".join(lines)


def scene_synopsis_summary(proposal: dict[str, Any]) -> str:
    """生成AIの過去の提案(画面に出す提案の対応表)を、会話の履歴に入れるための文。"""
    lines = []
    for scene in proposal.get("scenes") or []:
        title = (scene.get("title") or "").strip() or "(題は変えない)"
        lines.append(f"## 第{scene.get('act')}幕のシーン{scene.get('scene')}: {title}")
        if (scene.get("synopsis") or "").strip():
            lines.append(scene["synopsis"].strip())
    return "\n".join(lines)
