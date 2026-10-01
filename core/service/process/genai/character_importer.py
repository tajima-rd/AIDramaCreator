# core/service/process/genai/character_importer.py
"""
企画書の登場人物を、プロジェクトの人物(Character)として取り込む(docs/architecture.md 9節)。人物パネルのCharactersタブが使う。

- 企画書の登場人物とプロジェクトの人物は、名前(前後の空白は無視)が同じなら同じ人物とみなす(2026-10-02ユーザー)。
- 未登録なら、作業補助の生成AIに骨組みを作らせて新しい人物にする(create)。
- 登録済みなら、まず矛盾を確かめさせ(check_conflict)、利用者がキャンセル・統合(merge)・置き換え(replace)を選ぶ。
  置き換えは人物の識別子を保つので、人物関係・まとまりからのつながりと経歴は残る(置き換えるのは読み・性別・年齢・話し方・特徴)。
- 取り込んだ人物は、その作品の人物の参照(dramaturgy.characters)にも加える。
- 結果は生成AIの提案として下書きに反映する(Apply。確定は利用者がSave Versionで行う)。

生成AIはタスク(ScriptwriterのAgentTask.code)から選ぶ(llm_role。どちらも作業補助)。作品のScriptwriterの役割・厳守事項等を指示に含める。
"""

from enum import StrEnum
from typing import Any, Optional

import yaml

from core.infra.io.model_definition_reader import ModelDefinition, load_documents
from core.model.agent.base_agent import BaseAgent
from core.model.agent.scriptwriter import Scriptwriter
from core.model.drama import Character, Dramaturgy
from core.model.drama.proposal import ProposalCharacter
from core.project.project import Project
from core.prompt import character_import as prompts
from core.service.process.edit import drama_draft_editor
from core.service.process.genai.generator_builder import build_task_text_generator

# 新しい人物を、同じ部分YAMLの中で作品から参照するためのkey(参照は重ねた後のkeyで解決する。docs/database_design.md)
NEW_CHARACTER_KEY = "proposal_import_character"


class ImportMode(StrEnum):
    CREATE = "create"  # 未登録の人物を骨組みから作る
    MERGE = "merge"  # 登録済みの人物に、企画書の説明を統合する
    REPLACE = "replace"  # 登録済みの人物の設定を、企画書から作った骨組みで置き換える


class ConflictCheckOutcome:
    def __init__(self, character_id: str, conflict: bool, reasons: list[str]):
        self.character_id: str = character_id  # 登録済みの人物
        self.conflict: bool = conflict
        self.reasons: list[str] = reasons


class ImportOutcome:
    def __init__(self, revision: int, character_id: str):
        self.revision: int = revision  # 下書きの履歴の番号
        self.character_id: str = character_id  # 作った・更新した人物


def _same_name(a: Optional[str], b: Optional[str]) -> bool:
    return (a or "").strip() == (b or "").strip()


class _Target:
    """取り込みの対象(作品・企画書の登場人物・同じ名前の登録済みの人物)。"""

    def __init__(self, model: ModelDefinition, dramaturgy_id: str, name: str):
        name = (name or "").strip()
        if not name:
            raise ValueError("名前の無い登場人物は取り込めません。企画書で名前を付けてください。")
        dramaturgy: Optional[Dramaturgy] = next((d for d in model.dramaturgies if d.id == dramaturgy_id), None)
        if dramaturgy is None:
            raise ValueError(f"作品が見つかりません: {dramaturgy_id}")
        proposal_character: Optional[ProposalCharacter] = next(
            (c for c in dramaturgy.proposal.characters if _same_name(c.name, name)), None
        )
        if proposal_character is None:
            raise ValueError(f"企画書に登場人物「{name}」がいません。")
        registered = [c for c in model.characters if _same_name(c.name, name)]
        if len(registered) > 1:
            raise ValueError(f"「{name}」という名前の人物が{len(registered)}人登録されています。どちらかの名前を変えてください。")
        self.name: str = name
        self.dramaturgy: Dramaturgy = dramaturgy
        self.proposal_character: ProposalCharacter = proposal_character
        self.registered: Optional[Character] = registered[0] if registered else None
        self.scriptwriter: Optional[BaseAgent] = next((a for a in dramaturgy.agents if isinstance(a, Scriptwriter)), None)


def check_conflict(project: Project, db_path: str, draft_id: str, dramaturgy_id: str, name: str) -> ConflictCheckOutcome:
    """登録済みの人物の設定と、企画書の登場人物の説明が両立するかを、生成AIに確かめさせる(下書きは変えない)。"""
    target = _Target(drama_draft_editor.load_draft_model(db_path, draft_id), dramaturgy_id, name)
    if target.registered is None:
        raise ValueError(f"「{target.name}」はまだ登録されていません。")
    generator = build_task_text_generator(project, prompts.CONFLICT_TASK)
    response = generator.generate_structured(
        prompts.conflict_request(target.dramaturgy.proposal, target.proposal_character, target.registered),
        prompts.CharacterConflictResponse,
        system_instruction=prompts.conflict_prompt(target.scriptwriter),
    )
    reasons = [r.strip() for r in response.reasons if r.strip()]
    return ConflictCheckOutcome(target.registered.id, response.conflict or bool(reasons), reasons)


def import_character(
    project: Project, db_path: str, draft_id: str, dramaturgy_id: str, name: str, mode: ImportMode
) -> ImportOutcome:
    """企画書の登場人物を取り込み、下書きに反映する(Apply)。"""
    target = _Target(drama_draft_editor.load_draft_model(db_path, draft_id), dramaturgy_id, name)
    if mode is ImportMode.CREATE and target.registered is not None:
        raise ValueError(f"「{target.name}」は登録済みです。統合か置き換えを選んでください。")
    if mode is not ImportMode.CREATE and target.registered is None:
        raise ValueError(f"「{target.name}」はまだ登録されていません。")

    generator = build_task_text_generator(project, prompts.IMPORT_TASK)
    proposal = target.dramaturgy.proposal
    if mode is ImportMode.MERGE:
        request = prompts.merge_request(proposal, target.proposal_character, target.registered)
        instruction = prompts.merge_prompt(target.scriptwriter)
    else:
        request = prompts.sketch_request(proposal, target.proposal_character)
        instruction = prompts.sketch_prompt(target.scriptwriter)
    sketch = generator.generate_structured(request, prompts.CharacterSketch, system_instruction=instruction)

    content = _draft_content(db_path, draft_id)
    if mode is ImportMode.CREATE:
        character = {"key": NEW_CHARACTER_KEY, "name": target.name, **_character_fields(sketch, mode)}
        character_key = NEW_CHARACTER_KEY
    else:
        character = {"id": target.registered.id, **_character_fields(sketch, mode)}
        character_key = _character_key(content, target.registered.id)
    patch: dict[str, Any] = {"characters": [character]}
    references = _dramaturgy_character_refs(content, dramaturgy_id)
    if character_key not in references:
        # 作品の人物の参照は一覧で丸ごと置き換わる(docs/database_design.md)ので、今の参照に足して渡す
        patch["dramaturgies"] = [{"id": dramaturgy_id, "characters": [{"ref": key} for key in [*references, character_key]]}]
    revision = drama_draft_editor.apply_to_draft(db_path, draft_id, yaml.safe_dump(patch, allow_unicode=True, sort_keys=False))

    if target.registered is not None:
        return ImportOutcome(revision, target.registered.id)
    created = _Target(drama_draft_editor.load_draft_model(db_path, draft_id), dramaturgy_id, target.name).registered
    return ImportOutcome(revision, created.id)


def _draft_content(db_path: str, draft_id: str) -> dict[str, Any]:
    documents = load_documents(drama_draft_editor.draft_yaml(db_path, draft_id))
    return documents[0] if documents else {}


def _character_key(content: dict[str, Any], character_id: str) -> str:
    return next(c["key"] for c in content.get("characters", []) if c.get("id") == character_id)


def _dramaturgy_character_refs(content: dict[str, Any], dramaturgy_id: str) -> list[str]:
    dramaturgy = next(d for d in content.get("dramaturgies", []) if d.get("id") == dramaturgy_id)
    return [ref["ref"] for ref in dramaturgy.get("characters", [])]


def _blank_to_none(value: str) -> Optional[str]:
    value = (value or "").strip()
    return value or None


def _without_blank(values: dict[str, Optional[str]]) -> dict[str, str]:
    return {k: v for k, v in values.items() if v is not None}


def _character_fields(sketch: prompts.CharacterSketch, mode: ImportMode) -> dict[str, Any]:
    """骨組みを、部分YAMLの人物の属性にする。

    - create: 空の値は書かない
    - replace: 空の値はnull(登録済みの値を消す)。語尾の一覧も空にする(骨組みは語尾を作らないため)
    - merge: 空の値は書かない(登録済みの値を残す)。特徴が空なら特徴の一覧を書かない(登録済みの一覧を残す)
    """
    values = {
        "reading": _blank_to_none(sketch.reading),
        "gender": _blank_to_none(sketch.gender),
        "age": _blank_to_none(sketch.age),
    }
    speech = {
        "first_person": _blank_to_none(sketch.first_person),
        "tone": _blank_to_none(sketch.tone),
        "description": _blank_to_none(sketch.speech_description),
    }
    characteristics = [
        {
            "item": c.item.strip(),
            **_without_blank({"definition": _blank_to_none(c.definition), "description": _blank_to_none(c.description)}),
            "features": [
                {
                    "item": f.item.strip(),
                    **_without_blank(
                        {
                            "value": _blank_to_none(f.value),
                            "definition": _blank_to_none(f.definition),
                            "description": _blank_to_none(f.description),
                        }
                    ),
                }
                for f in c.features
                if f.item.strip()
            ],
        }
        for c in sketch.characteristics
        if c.item.strip()
    ]
    if mode is ImportMode.REPLACE:
        return {**values, "speech_style": {**speech, "endings": []}, "characteristics": characteristics}
    fields: dict[str, Any] = _without_blank(values)
    speech_values = _without_blank(speech)
    if speech_values:
        fields["speech_style"] = speech_values
    if characteristics or mode is ImportMode.CREATE:
        fields["characteristics"] = characteristics
    return fields
