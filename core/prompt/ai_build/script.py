# core/prompt/ai_build/script.py
"""
Build with AIの読み上げ台本の工程(Script。docs/architecture.md 10節)。相談相手はScriptwriter、タスクはwrite_dialogue。

右側で選んだ1つのシーンの台詞(Scene.script。話者と台詞の並び)を書く。演出付きの原稿(Scene.elements。Director)は扱わない。
話者は作品の配役にいる人物だけ(生成AIは人物の名前で指す)。提案は、そのシーンの台詞の全体(並びごと置き換える)。
演出付きの原稿があるシーンは断る(原稿は台詞を識別子で参照するため)。
"""

from typing import Any, Optional

from pydantic import BaseModel, Field

from core.genai.prompt import BulletInstruction, ForbiddenRule, MandatoryRule, Prompt, Section
from core.model.agent.base_agent import BaseAgent
from core.model.drama import Dramaturgy, Scene
from core.prompt.agent_instruction import agent_task_sections
from core.prompt.ai_build.casting import cast_text
from core.prompt.ai_build.common import COMMON_RULES, BuildMode, EvidenceItem
from core.prompt.ai_build.scene_synopsis import scene_text
from core.prompt.ai_build.synopsis import ordered_acts, ordered_scenes
from core.prompt.drama_production.dialogue import character_profile

TASK = "write_dialogue"

# 前のシーンの台詞のうち、つながりを見せるために渡す末尾の行数
PREVIOUS_LINES = 5


class LineDraft(BaseModel):
    speaker: str = Field(description="話す人物の名前(「話せる人物」の名前のまま)")
    text: str = Field(description="台詞(話す言葉だけ。ト書き・話者の名前・括弧書きの動作は書かない)")


class ScriptReply(BaseModel):
    message: str = Field(description="利用者への返事")
    has_proposal: bool = Field(description="台詞を変える提案があればtrue")
    lines: list[LineDraft] = Field(
        description="提案した後の、このシーンの台詞の全体(話す順)。提案が無ければ空"
    )
    evidence: list[EvidenceItem] = Field(description="根拠。無ければ空")
    questions: list[str] = Field(description="利用者への質問。無ければ空")
    warnings: list[str] = Field(description="利用者が確かめるとよい注意。無ければ空")


GUIDE = [
    "音声ドラマとして読み上げる、このシーンの台詞(人物どうしの掛け合い)を書く。",
    "シーンのあらすじに従い、別の話を混ぜない。作品と幕のあらすじ、前後のシーンと流れがつながるようにする。",
    "台詞の口調には、人物の一人称・口調・語尾・話し方と、人物関係の呼び方・口調を深く反映させる。配役の演じ方も参考にする。",
    "シーンの場所に「この場所で案内すること」があれば、人物の台詞の中で聞き手に案内する。「この場所の事実」と食い違うことを言わせない。",
    "台詞だけで場面が伝わるように書く(音声だけの作品なので、場所・状況・動作も台詞で伝える)。",
    "長さは利用者の指定に従う。指定が無ければ、あらすじを過不足なく描ける長さ(目安は台詞全体で350字程度)にする。",
    "台詞は、作品の入力の言語(無ければ利用者の言語)で書く。",
]

ONE_SHOT_RULES = [
    "利用者の要望・資料・シーンの設定・今の台詞から、このシーンの台詞の全体を1回で書き、has_proposalをtrueにする。",
    "今の台詞に良いところがあれば活かす。",
    "返事(message)には、書いた内容の要点と、利用者が確かめるとよい点を短く書く。",
]

DIALOGUE_RULES = [
    "利用者と相談する。考えや選択肢を示し、利用者の判断を助ける。",
    "台詞を変える提案があるときだけhas_proposalをtrueにし、linesに変えた後の台詞の全体(変えない行もそのまま)を入れる。",
    "提案が無いときはhas_proposalをfalseにし、linesは空にする。",
    "利用者が求めていない行を勝手に変えない。",
]

PROHIBITIONS = [
    "「話せる人物」にいない人物に話させない(ナレーターも、配役に無ければ使わない)。",
    "台詞(text)に、話者の名前・ト書き・(ため息をつく)のような括弧書きの動作・演出の指示を書かない。",
    "シーンの設定(あらすじ・場所・時期・状況)と人物の設定を書き換えない。",
]


def script_prompt(agent: Optional[BaseAgent], mode: BuildMode) -> Prompt:
    rules = COMMON_RULES + (ONE_SHOT_RULES if mode is BuildMode.ONE_SHOT else DIALOGUE_RULES)
    title = (
        "シーンの台詞をワンショットで下書きする"
        if mode is BuildMode.ONE_SHOT
        else "シーンの台詞について利用者と相談する"
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


def _script_lines(scene: Scene, last: Optional[int] = None) -> list[str]:
    lines = sorted(scene.script.lines, key=lambda line: line.order)
    if last is not None:
        lines = lines[-last:]
    return [f"{line.cast.character.name}: {line.text}" for line in lines]


def scene_position(dramaturgy: Dramaturgy, scene_id: str) -> tuple[int, int, list[tuple[int, int, Scene]]]:
    """シーンの幕の番号・シーンの番号(どちらも1から)と、作品のすべてのシーン((幕の番号, シーンの番号, シーン)の並び)。
    シーンが無ければValueError。"""
    entries = [
        (act_number, scene_number, scene)
        for act_number, act in enumerate(ordered_acts(dramaturgy), start=1)
        for scene_number, scene in enumerate(ordered_scenes(act), start=1)
    ]
    for act_number, scene_number, scene in entries:
        if scene.id == scene_id:
            return act_number, scene_number, entries
    raise ValueError(f"シーンが見つかりません: {scene_id}")


def script_context(dramaturgy: Dramaturgy, scene_id: str) -> str:
    """生成AIに渡す今の内容(作品と幕のあらすじ・前後のシーン・対象のシーンの設定・話せる人物と配役・今の台詞)。"""
    act_number, scene_number, entries = scene_position(dramaturgy, scene_id)
    if not dramaturgy.casts:
        raise ValueError("配役がありません。台詞を書く前に、Castingの工程で配役を作ってください。")
    index = next(i for i, (_, _, s) in enumerate(entries) if s.id == scene_id)
    scene = entries[index][2]
    if scene.elements:
        # 演出付きの原稿は台詞(Line)を識別子で参照するので、台詞を置き換えると食い違う
        raise ValueError("このシーンには演出付きの原稿があります。台詞を書き換えると原稿と食い違うので、ここでは書きません。")
    act = ordered_acts(dramaturgy)[act_number - 1]

    lines = [f"# 作品: {dramaturgy.title}"]
    if dramaturgy.input_language:
        lines.append(f"(作品の入力の言語: {dramaturgy.input_language})")
    lines += ["", "## 作品全体のあらすじ", dramaturgy.synopsis or "(まだ無い)"]
    lines += ["", f"## 第{act_number}幕: {act.title or '(題なし)'}", act.synopsis or "(あらすじはまだ無い)"]

    if index > 0:
        prev_act, prev_scene, previous = entries[index - 1]
        lines += ["", f"# 前のシーン(第{prev_act}幕のシーン{prev_scene}): {previous.title or '(題なし)'}"]
        lines.append(previous.synopsis or "(あらすじはまだ無い)")
        tail = _script_lines(previous, PREVIOUS_LINES)
        if tail:
            lines += ["(台詞の終わり)", *tail]
    if index + 1 < len(entries):
        next_act, next_scene, following = entries[index + 1]
        lines += ["", f"# 次のシーン(第{next_act}幕のシーン{next_scene}): {following.title or '(題なし)'}"]
        lines.append(following.synopsis or "(あらすじはまだ無い)")

    lines += ["", f"# 台詞を書くシーン(第{act_number}幕のシーン{scene_number})"]
    lines += scene_text(scene_number, scene)

    lines += ["", "# 話せる人物(配役)"]
    lines += [cast_text(cast) for cast in dramaturgy.casts]
    lines += ["", "# 話せる人物の設定"]
    # 人物設定の見出し(#・##)を、この節の下の深さ(###・####)にする
    lines += [("##" + character_profile(cast.character)).replace("\n## ", "\n#### ") for cast in dramaturgy.casts]

    lines += ["", "# このシーンの今の台詞"]
    lines += _script_lines(scene) or ["(まだ無い)"]
    return "\n".join(lines)


def script_summary(proposal: dict[str, Any]) -> str:
    """生成AIの過去の提案(画面に出す提案の対応表)を、会話の履歴に入れるための文。"""
    return "\n".join(f"{line.get('speaker')}: {line.get('text')}" for line in proposal.get("lines") or [])
