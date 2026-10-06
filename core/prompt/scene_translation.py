# core/prompt/scene_translation.py
"""
シーンの台詞の翻訳(Dramaturgy EditorのScenesタブのTranslation)のプロンプトと、生成AIに返させる構造。担当はStageManager、
タスクはtranslate(docs/model_design.md)。生成AIは呼ばない(呼ぶのはcore.service.process.genai.scene_translator)。

訳すのは、台詞ごとの原稿の音声にする文(感情タグ入り。原稿が無い・今の台詞と食い違うなら台詞)。訳す言語は利用者が選ぶ(いくつでも。
2026-10-06ユーザー)。同じ所に同じ感情タグを挿む。訳文はRecordingでその言語の音声を作るときに読む(Dialogue.translations)。
"""

from typing import Optional

from pydantic import BaseModel, Field

from core.genai.prompt import BulletInstruction, ForbiddenRule, MandatoryRule, Prompt, Section
from core.model.agent.base_agent import BaseAgent
from core.model.drama import Dramaturgy, Scene
from core.model.drama.script import Line
from core.prompt.agent_instruction import agent_task_sections
from core.prompt.ai_build.direction import AUDIO_TAGS, bare_text, dialogue_of, ordered_lines
from core.prompt.ai_build.scene_synopsis import scene_text
from core.prompt.drama_production.dialogue import character_profile

TASK = "translate"


class LineTranslation(BaseModel):
    number: int = Field(description="台詞の番号(「訳す台詞」の番号。1から)")
    translated_text: str = Field(description="訳文(元の文と同じ所に同じ感情タグを挿む)")


class SceneTranslationReply(BaseModel):
    translations: list[LineTranslation] = Field(description="すべての台詞の訳文(台詞の順)")
    warnings: list[str] = Field(description="利用者が確かめるとよい注意(訳しにくい言葉・地名の読み等)。無ければ空")


GUIDE = [
    "音声ドラマの台詞を、指定された言語へ訳す。訳文はそのまま音声合成で読み上げる。",
    "話し言葉に訳す。人物の性格・年齢・口調・一人称と、相手への呼び方・口調(人物関係)が訳文でも伝わるようにする。",
    "元の文の感情タグ(" + ", ".join(AUDIO_TAGS) + ")は、訳文の同じ所(文頭・文末・感情の変わり目)に同じものを挿む。タグの文字は訳さない。",
    "地名・人名・施設名は、その言語で通じる書き方にする(定まった訳が無ければ読みを写す)。",
    "シーンの場所・状況・あらすじと、前後の台詞の流れに合う訳にする。",
]

RULES = [
    "「訳す台詞」のすべての台詞を、番号と一緒に1つずつ返す。",
    "迷った言葉・訳しにくい言葉があれば、注意(warnings)に書く。",
]

PROHIBITIONS = [
    "台詞を足したり、まとめたり、削ったりしない。",
    "一覧に無い感情タグを作らない。訳文に、話者の名前・ト書き・訳注を書かない。",
]


def translation_prompt(agent: Optional[BaseAgent]) -> Prompt:
    return Prompt(
        components=[
            *agent_task_sections(agent, TASK),
            Section(
                title="シーンの台詞を訳す",
                children=[
                    BulletInstruction(items=GUIDE),
                    MandatoryRule(BulletInstruction(items=RULES)),
                    ForbiddenRule(BulletInstruction(items=PROHIBITIONS)),
                ],
            ),
        ]
    )


def source_text(scene: Scene, line: Line) -> str:
    """訳す元の文(原稿の音声にする文。原稿が無い・今の台詞と食い違う(原稿の後に台詞を直した)なら台詞)。"""
    dialogue = dialogue_of(scene, line)
    if dialogue is not None and dialogue.text and bare_text(dialogue.text) == bare_text(line.text):
        return dialogue.text
    return line.text


def translation_context(dramaturgy: Dramaturgy, scene: Scene, scene_number: int, source: str, target: str) -> str:
    """生成AIに渡す内容(言語・シーンの設定・話す人物の設定・番号付きの台詞)。source・targetは言語の名前(例: 日本語(ja))。"""
    lines = ordered_lines(scene)
    text = [
        f"# 訳す言語: {source} → {target}",
        "",
        "# シーン",
        *scene_text(scene_number, scene),
    ]
    speakers = []
    for line in lines:
        if line.cast not in speakers:
            speakers.append(line.cast)
    text += ["", "# 話す人物の設定"]
    # 人物設定の見出し(#・##)を、この節の下の深さ(###・####)にする
    text += [("##" + character_profile(cast.character)).replace("\n## ", "\n#### ") for cast in speakers]
    text += ["", "# 訳す台詞"]
    text += [
        f"{number}. {line.cast.character.name}: {source_text(scene, line)}"
        for number, line in enumerate(lines, start=1)
    ]
    return "\n".join(text)
