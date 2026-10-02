# core/prompt/ai_build/characters.py
"""
Build with AIの人物の工程(Characters・Groups・Relationships。docs/architecture.md 10節)。相談相手はScriptwriter。

- Characters(create_character): 企画書とプロジェクトの人物から、この作品の人物の一覧を作る。まとまりと人物関係も大まかに作る
- Groups(create_character_group): 人物のまとまりの詳細を固める
- Relationships(create_relationship): 人物関係の詳細を固める

人物・まとまり・関係はプロジェクト(世界観)のもの。生成AIは識別子を決めず、既存の要素を名前で指す(同じ名前なら更新、無ければ追加)。
生成AIには削除させない(削除は利用者が人物パネルで行う)。経歴と人物関係の時期は、時期の設定が要るので扱わない
(企画書の取り込みと同じ)。設定の少ない人物は不備ではない(docs/overview.md「世界観が先、作品は後」)。
"""

from typing import Optional

from pydantic import BaseModel, Field

from core.genai.prompt import BulletInstruction, ForbiddenRule, MandatoryRule, Prompt, Section
from core.infra.io.model_definition_reader import ModelDefinition
from core.model.agent.base_agent import BaseAgent
from core.model.drama import Dramaturgy
from core.prompt.agent_instruction import agent_task_sections
from core.prompt.ai_build.common import COMMON_RULES, BuildMode, EvidenceItem
from core.prompt.character_import import CharacteristicSketch, proposal_text
from core.prompt.drama_production.dialogue import character_profile

CHARACTERS_TASK = "create_character"
GROUPS_TASK = "create_character_group"
RELATIONSHIPS_TASK = "create_relationship"


class CharacterDraft(BaseModel):
    """人物(追加か更新)。分からない値・変えない値は空文字。"""

    name: str = Field(description="人物の名前。既存の人物を更新するときは、その名前のまま")
    reading: str = Field(description="名前の読み(かな)。分からなければ空文字")
    gender: str = Field(description="性別。分からなければ空文字")
    age: str = Field(description="年齢・年代(例: 40代)。分からなければ空文字")
    first_person: str = Field(description="一人称。分からなければ空文字")
    tone: str = Field(description="相手を問わない既定の口調。分からなければ空文字")
    speech_description: str = Field(description="話し方の説明。無ければ空文字")
    characteristics: list[CharacteristicSketch] = Field(
        description="人物像の特徴。既存の人物を更新するときは、変えない特徴も含めた全体。変えないなら空の一覧"
    )


class GroupDraft(BaseModel):
    name: str = Field(
        description="まとまりの名前(例: 佐藤家)。既存のまとまりを更新するときは、その名前のまま"
    )
    kind: str = Field(description="まとまりの種類(例: 家族・職場)。分からなければ空文字")
    description: str = Field(description="まとまりの説明。無ければ空文字")
    members: list[str] = Field(description="メンバーの人物の名前")


class RelationshipDraft(BaseModel):
    source: str = Field(description="関係の起点の人物の名前")
    target: str = Field(description="関係の相手の人物の名前")
    label: str = Field(description="sourceから見たtargetとの関係の名前(例: 父・上司・幼なじみ)")
    description: str = Field(description="関係の説明。無ければ空文字")
    form_of_address: str = Field(
        description="sourceがtargetを呼ぶときの呼び方。分からなければ空文字"
    )
    tone: str = Field(description="sourceがtargetに話すときの口調。分からなければ空文字")


class _Reply(BaseModel):
    message: str = Field(description="利用者への返事")
    has_proposal: bool = Field(description="追加・変更の提案があればtrue")
    evidence: list[EvidenceItem] = Field(description="根拠。無ければ空")
    questions: list[str] = Field(description="利用者への質問。無ければ空")
    warnings: list[str] = Field(description="利用者が確かめるとよい注意。無ければ空")


class CharactersReply(_Reply):
    characters: list[CharacterDraft] = Field(description="追加・更新する人物。提案が無ければ空")
    groups: list[GroupDraft] = Field(description="追加・更新するまとまり(大まかでよい)。無ければ空")
    relationships: list[RelationshipDraft] = Field(
        description="追加・更新する人物関係(大まかでよい)。無ければ空"
    )


class GroupsReply(_Reply):
    groups: list[GroupDraft] = Field(description="追加・更新するまとまり。提案が無ければ空")


class RelationshipsReply(_Reply):
    relationships: list[RelationshipDraft] = Field(
        description="追加・更新する人物関係。提案が無ければ空"
    )


WORLD_GUIDE = [
    "人物・人物のまとまり・人物関係は、プロジェクト(世界観)のもので、複数の作品で共有する。どの作品にも出ない人物、設定の少ない人物がいてもよい。",
    "提案には、追加する要素と変える要素だけを入れる。変えない要素は入れない。",
    "既存の人物・まとまり・関係は名前で指す(人物関係は、起点・相手の人物の名前と関係の名前で指す)。名前を変えない。",
    "人物・まとまり・関係を削除しない(削除は利用者が行う)。",
    "人物の名前は企画書・既存の人物の名前と同じ表記にする。",
]

WORLD_PROHIBITIONS = [
    "経歴・人物関係の時期を作らない(時期の設定が要るため、別の作業で作る)。",
    "識別子(id・key)を書かない。",
]

STEP_RULES = {
    CHARACTERS_TASK: [
        "企画書の登場人物を中心に、この作品の人物の一覧を作る。プロジェクトに登録済みの同じ名前の人物は、その設定を土台にして更新として返す。",
        "人物のまとまり(家族・職場等)と人物関係も、大まかに作る(まとまりは名前とメンバー、関係は誰から誰へと関係の名前)。詳細は別の工程で固める。",
    ],
    GROUPS_TASK: [
        "人物のまとまりの名前・種類・説明・メンバーを固める。メンバーは登録済みの人物の名前で書く(人物はこの工程では作らない)。",
        "既存のまとまりを更新するときは、メンバーの全体を返す。",
    ],
    RELATIONSHIPS_TASK: [
        "人物関係の、関係の名前・説明・呼び方・口調を固める。起点と相手は登録済みの人物の名前で書く(人物はこの工程では作らない)。",
        "関係には向きがある。AからBへの関係と、BからAへの関係は別に書く(例: 父から娘へ「娘」、娘から父へ「父」)。",
    ],
}

TITLES = {
    CHARACTERS_TASK: "人物を作る",
    GROUPS_TASK: "人物のまとまりを固める",
    RELATIONSHIPS_TASK: "人物関係を固める",
}

ONE_SHOT_RULES = [
    "利用者の要望・企画書・今の人物の設定から、この工程の内容を1回で作り、has_proposalをtrueにする。",
    "返事(message)には、作った内容の要点と、利用者が確かめるとよい点を短く書く。",
]

DIALOGUE_RULES = [
    "利用者と相談する。考えや選択肢を示し、利用者の判断を助ける。",
    "追加・変更の提案があるときだけhas_proposalをtrueにする。提案が無いときはfalseにし、提案の欄は空にする。",
    "利用者が提案だけを聞きたいときは、返事(message)で答え、has_proposalをfalseにする。",
    "利用者が求めていない要素を勝手に変えない。",
]

REPLIES: dict[str, type[_Reply]] = {
    CHARACTERS_TASK: CharactersReply,
    GROUPS_TASK: GroupsReply,
    RELATIONSHIPS_TASK: RelationshipsReply,
}


def world_prompt(agent: Optional[BaseAgent], task_code: str, mode: BuildMode) -> Prompt:
    rules = (
        COMMON_RULES
        + STEP_RULES[task_code]
        + (ONE_SHOT_RULES if mode is BuildMode.ONE_SHOT else DIALOGUE_RULES)
    )
    return Prompt(
        components=[
            *agent_task_sections(agent, task_code),
            Section(
                title=TITLES[task_code],
                children=[
                    BulletInstruction(items=WORLD_GUIDE),
                    MandatoryRule(BulletInstruction(items=rules)),
                    ForbiddenRule(BulletInstruction(items=WORLD_PROHIBITIONS)),
                ],
            ),
        ]
    )


def world_context(model: ModelDefinition, dramaturgy: Dramaturgy) -> str:
    """生成AIに渡す今の内容(企画書・この作品の登場人物・プロジェクトの人物・まとまり・人物関係)。"""
    lines = [proposal_text(dramaturgy.proposal)]
    names = [c.name for c in dramaturgy.characters]
    lines += ["", "# この作品の登場人物", ", ".join(names) if names else "(まだいない)"]
    lines += ["", "# プロジェクトの人物"]
    # 人物設定の見出し(#・##)を、この節の下の深さ(###・####)にする
    lines += [
        ("##" + character_profile(c)).replace("\n## ", "\n#### ") for c in model.characters
    ] or ["(まだいない)"]
    lines += ["", "# 人物のまとまり"]
    lines += [
        f"* {g.name}"
        + (f"({g.kind})" if g.kind else "")
        + f": {', '.join(m.name for m in g.members) or '(メンバーなし)'}"
        + (f" — {g.description}" if g.description else "")
        for g in model.character_groups
    ] or ["(まだない)"]
    lines += ["", "# 人物関係"]
    lines += [
        f"* {r.source.name} → {r.target.name}: {r.label}"
        + "".join(
            f" / {label}: {value}"
            for label, value in (
                ("呼び方", r.form_of_address),
                ("口調", r.tone),
                ("説明", r.description),
            )
            if value
        )
        for r in model.relationships
    ] or ["(まだない)"]
    return "\n".join(lines)
