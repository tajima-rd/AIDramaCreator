# core/prompt/ai_build/direction.py
"""
Build with AIの演出付きの原稿の工程(Direction。docs/architecture.md 10節)。相談相手はDirector、タスクはdirect_scene。

右側で選んだ1つのシーンの台詞(Scene.script)の1行ごとに、演出付きの台詞(Scene.elementsのDialogue)を作る: 音声にする文
(台詞の文言は変えず、音声合成の感情タグだけを挿む)・ト書き・演出(話し方・速さ・強弱・感情・後の間)。音声合成はこの原稿から作る。
訳文は作らない(翻訳はStageManagerの担当。Dramaturgy EditorのScenesタブのTranslationで、言語ごとに作る。2026-10-06ユーザー)。
効果音・環境音・BGMは扱わない(モデルに中身の属性がまだ無い)。台詞は番号(1から)で指す。
"""

import re
from typing import Any, Optional

from pydantic import BaseModel, Field

from core.genai.prompt import BulletInstruction, ForbiddenRule, MandatoryRule, Prompt, Section
from core.model.agent import Actor
from core.model.agent.base_agent import BaseAgent
from core.model.drama import Dramaturgy, Scene
from core.model.drama.script import Line
from core.model.drama.script_element import Dialogue
from core.prompt.agent_instruction import agent_task_sections
from core.prompt.ai_build.casting import cast_text
from core.prompt.ai_build.common import COMMON_RULES, BuildMode, EvidenceItem
from core.prompt.ai_build.scene_synopsis import scene_text
from core.prompt.ai_build.script import scene_position
from core.prompt.drama_production.dialogue import character_profile

TASK = "direct_scene"

# 音声合成(Gemini)の感情タグ。音声にする文に挿めるのはこれだけ(旧来の原稿の生成と同じ18種)
AUDIO_TAGS = [
    "[amazed]",
    "[crying]",
    "[curious]",
    "[excited]",
    "[sighs]",
    "[gasp]",
    "[giggles]",
    "[laughs]",
    "[mischievously]",
    "[panicked]",
    "[sarcastic]",
    "[serious]",
    "[shouting]",
    "[tired]",
    "[trembling]",
    "[whispers]",
    "[very_fast]",
    "[very_slow]",
]


_TAG = re.compile(r"\[[^\]]*\]")


def remove_unknown_tags(text: str) -> tuple[str, list[str]]:
    """一覧(AUDIO_TAGS)に無い感情タグを外した文と、外したタグ。"""
    unknown = [tag for tag in _TAG.findall(text) if tag not in AUDIO_TAGS]
    for tag in unknown:
        text = text.replace(tag, "")
    return re.sub(r"[ \t]{2,}", " ", text).strip(), unknown


def bare_text(text: str) -> str:
    """感情タグと空白を除いた文(音声にする文と台詞の文言の照合に使う)。"""
    return re.sub(r"\s", "", _TAG.sub("", text or ""))


class DialogueDirectionDraft(BaseModel):
    """台詞1行の演出。決めない値は空文字。"""

    number: int = Field(description="台詞の番号(「このシーンの台詞」の番号。1から)")
    text: str = Field(description="音声にする文。台詞の文言をそのまま使い、感情タグだけを挿む")
    action: str = Field(description="ト書き(動作・表情・周りの様子。英語)。無ければ空文字")
    style: str = Field(description="話し方(英語。例: Warm and welcoming)。無ければ空文字")
    pace: str = Field(description="速さ(Slow・Moderate・Fastのどれか)。無ければ空文字")
    dynamics: str = Field(description="強弱(英語。例: Soft, rising at the end)。無ければ空文字")
    emotion: str = Field(description="感情(英語。例: Relieved)。無ければ空文字")
    pause_after: str = Field(description="この台詞の後の間(Short・Medium・Longのどれか)。無ければ空文字")


class DirectionReply(BaseModel):
    message: str = Field(description="利用者への返事")
    has_proposal: bool = Field(description="原稿を変える提案があればtrue")
    dialogues: list[DialogueDirectionDraft] = Field(
        description="提案した後の、このシーンのすべての台詞の演出(台詞の順)。提案が無ければ空"
    )
    evidence: list[EvidenceItem] = Field(description="根拠。無ければ空")
    questions: list[str] = Field(description="利用者への質問。無ければ空")
    warnings: list[str] = Field(description="利用者が確かめるとよい注意。無ければ空")


GUIDE = [
    "このシーンの台詞の1行ごとに、音声合成に渡す演出付きの台詞を作る。音声はこの原稿から作る。",
    "音声にする文(text)は、台詞の文言を1字も変えずに使い、感情・話し方の変わり目(文頭・文末・途中)に感情タグを挿む。"
    "使える感情タグは次のものだけ: " + ", ".join(AUDIO_TAGS) + "。1つの台詞に複数挿んでも、挿まなくてもよい。",
    "ト書き(action)と演出(style・dynamics・emotion)は、音声合成への指示なので英語で、具体的に短く書く。"
    "速さ(pace)はSlow・Moderate・Fast、後の間(pause_after)はShort・Medium・Longのどれかにする。演出は抽象的な言葉で表す(ミリ秒等の数値にしない)。",
    "人物の性格・年齢・話し方、配役の演じ方・話す速さ・訛り、シーンの場所・状況・あらすじ、前後の台詞の流れから演出を決める。",
]

ONE_SHOT_RULES = [
    "利用者の要望・資料・シーンの設定・台詞・今の原稿から、このシーンのすべての台詞の演出を1回で作り、has_proposalをtrueにする。",
    "今の原稿に良いところがあれば活かす。",
    "返事(message)には、演出の要点と、利用者が確かめるとよい点を短く書く。",
]

DIALOGUE_RULES = [
    "利用者と相談する。考えや選択肢を示し、利用者の判断を助ける。",
    "原稿を変える提案があるときだけhas_proposalをtrueにし、dialoguesに変えた後のすべての台詞の演出(変えない台詞もそのまま)を入れる。",
    "提案が無いときはhas_proposalをfalseにし、dialoguesは空にする。",
    "利用者が求めていない台詞の演出を勝手に変えない。",
]

PROHIBITIONS = [
    "台詞の文言を変えない(足す・削る・言い換える・句読点を変えることもしない)。変えたいときは、返事で利用者に提案する。",
    "一覧に無い感情タグを作らない。",
    "台詞を増やしたり減らしたりしない(「このシーンの台詞」に無い番号を書かない)。",
]


def direction_prompt(agent: Optional[BaseAgent], mode: BuildMode) -> Prompt:
    rules = COMMON_RULES + (ONE_SHOT_RULES if mode is BuildMode.ONE_SHOT else DIALOGUE_RULES)
    title = (
        "シーンの演出付きの原稿をワンショットで下書きする"
        if mode is BuildMode.ONE_SHOT
        else "シーンの演出付きの原稿について利用者と相談する"
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


def ordered_lines(scene: Scene) -> list[Line]:
    """シーンの台詞を並びの順に(n番目が「台詞n+1」)。"""
    return sorted(scene.script.lines, key=lambda line: line.order)


def dialogue_of(scene: Scene, line: Line) -> Optional[Dialogue]:
    """台詞の行に対応する、演出付きの台詞(無ければNone)。"""
    return next((e for e in scene.elements if isinstance(e, Dialogue) and e.line_id == line.id), None)


def _direction_text(dialogue: Dialogue) -> str:
    direction = dialogue.direction
    facts = [
        ("音声にする文", dialogue.text),
        ("ト書き", dialogue.action),
        ("話し方", direction.style),
        ("速さ", direction.pace),
        ("強弱", direction.dynamics),
        ("感情", direction.emotion),
        ("後の間", direction.pause_after),
    ]
    return " / ".join(f"{label}: {value}" for label, value in facts if value)


def direction_context(dramaturgy: Dramaturgy, scene_id: str) -> str:
    """生成AIに渡す今の内容(シーンの設定・話す人物の配役と設定・台詞・今の原稿)。"""
    act_number, scene_number, entries = scene_position(dramaturgy, scene_id)
    scene = next(s for _, _, s in entries if s.id == scene_id)
    lines = ordered_lines(scene)
    if not lines:
        raise ValueError("このシーンには台詞がありません。先にScriptの工程で台詞を書いてください。")

    text = [f"# 作品: {dramaturgy.title}", f"(台詞の言語: {dramaturgy.input_language or '(未設定)'})"]
    text += ["", f"# 原稿を作るシーン(第{act_number}幕のシーン{scene_number})"]
    text += scene_text(scene_number, scene)

    speakers = []
    for line in lines:
        if line.cast not in speakers:
            speakers.append(line.cast)
    actors = {a.casting_id: a for a in dramaturgy.agents if isinstance(a, Actor)}
    text += ["", "# 話す人物(配役)"]
    text += [cast_text(cast, actors.get(cast.id)) for cast in speakers]
    text += ["", "# 話す人物の設定"]
    # 人物設定の見出し(#・##)を、この節の下の深さ(###・####)にする
    text += [("##" + character_profile(cast.character)).replace("\n## ", "\n#### ") for cast in speakers]

    text += ["", "# このシーンの台詞"]
    text += [f"{number}. {line.cast.character.name}: {line.text}" for number, line in enumerate(lines, start=1)]
    text += ["", "# 今の原稿(演出)"]
    current = [
        f"{number}. {_direction_text(dialogue)}"
        for number, line in enumerate(lines, start=1)
        if (dialogue := dialogue_of(scene, line)) is not None
    ]
    text += current or ["(まだ無い)"]
    return "\n".join(text)


def direction_summary(proposal: dict[str, Any]) -> str:
    """生成AIの過去の提案(画面に出す提案の対応表)を、会話の履歴に入れるための文。"""
    rows = []
    for item in proposal.get("dialogues") or []:
        facts = [
            item.get("text"),
            *(f"{key}: {item.get(key)}" for key in ("action", "style", "pace", "dynamics", "emotion", "pause_after") if item.get(key)),
        ]
        rows.append(f"{item.get('number')}. " + " / ".join(f for f in facts if f))
    return "\n".join(rows)
