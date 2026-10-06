# core/service/process/genai/ai_builder.py
"""
Build with AI(生成AIと相談しながら作品を作るパネル。docs/architecture.md 10節)の処理。

- 工程(タブ)ごとに、相談相手のエージェントとタスクが決まる(core.prompt.ai_build.step)。シーンごとの工程(Script)は、選んだシーン
  (scene_id)が対象で、会話の履歴もそのシーンの発言だけ。エージェントは作品のもの
  (Agentsタブで書いた役割・厳守事項等)を使い、作品にいなければプロジェクトのユーザー既定から作る。
- 生成AIはタスクの役割(llm_role)で選ぶ。渡すのは、工程の指示(システム)・今の工程の会話の履歴・最新の発言に添えた今の内容と資料。
  資料は、生成AIがその種類をそのまま読めれば添付し、読めなければテキストにして本文に入れる(QIDMと同じ)。
- 生成AIの提案は、下書きへ重ねる部分YAMLにして会話と一緒に記録する(core.infra.store.ai_build_store)。提案はApplyするまで
  作品に入らない。Applyは編集用の下書きに重ね(drama_draft_editor.apply_to_draft)、Undoは下書きの最後の変更を戻す。
- 生成AIの呼び出しに失敗したら何も記録しない(送り直せる)。
- 2つのモード(core.prompt.ai_build.common.BuildMode): ワンショット下書きは工程の内容を丸ごと置き換える提案(空の項目は消す)。
  対話は変わった項目だけの提案(生成AIが空で返した項目は「変えない」と扱う)。
"""

from typing import Any, Optional

import yaml

from core.genai import Attachment, Message, TextConfig, TextGenerator
from core.genai.rag.document_reader import document_text
from core.infra.io.model_definition_reader import build_model_definition_from_yaml, load_documents
from core.infra.store import agent_default_store, ai_build_store
from core.infra.store.ai_build_store import APPLIED, PENDING, UNDONE, StoredMessage
from core.model.agent.base_agent import BaseAgent
from core.model.agent.factory import AGENT_ROLES
from core.model.drama import Dramaturgy
from core.project.project import Project
from core.prompt.ai_build import casting as casting_prompts
from core.prompt.ai_build import characters as world_prompts
from core.prompt.ai_build import direction as direction_prompts
from core.prompt.ai_build import proposal as proposal_prompts
from core.prompt.ai_build import scene_synopsis as scene_synopsis_prompts
from core.prompt.ai_build import script as script_prompts
from core.prompt.ai_build import synopsis as synopsis_prompts
from core.prompt.ai_build.common import BuildMode
from core.prompt.ai_build.step import BuildStep, find_step
from core.service.process.edit import drama_draft_editor
from core.service.process.genai import voice_catalog
from core.service.process.genai.ai_build_patch import (
    PatchOutcome,
    audition_patch,
    cast_patch,
    direction_patch,
    proposal_patch,
    scene_synopsis_patch,
    script_patch,
    synopsis_patch,
    world_patch,
)
from core.service.process.genai.generator_builder import build_task_text_generator

# 応答の長さの上限。生成AIが同じ語を繰り返す状態に陥っても、上限で止めて「途中で切れた」と知らせる(上限が無いと、
# Gemmaで10分以上止まらなかった。2026-10-02)。企画書の応答は数千字なので、十分に余裕がある
MAX_OUTPUT_TOKENS = 8192


class ReferenceFile:
    """生成AIに渡す資料(Datasetのファイル)。"""

    def __init__(self, file_id: str, filename: str, path: str, file_format: str, media_type: str):
        self.file_id: str = file_id
        self.filename: str = filename
        self.path: str = path
        self.file_format: str = file_format
        self.media_type: str = media_type


def send_message(
    project: Project,
    draft_id: str,
    dramaturgy_id: str,
    step_key: str,
    scene_id: Optional[str],
    mode: BuildMode,
    text: str,
    references: list[ReferenceFile],
) -> StoredMessage:
    """利用者の発言を生成AIに送り、返事(と提案)を記録して返す。下書きは変えない。scene_idはシーンごとの工程の対象のシーン。"""
    step = find_step(step_key)
    scene_id = _scene_id(step, scene_id)
    db_path = project.layout.project_db_path
    text = (text or "").strip()
    if mode is BuildMode.DIALOGUE and not text:
        raise ValueError("発言を入力してください。")
    model = drama_draft_editor.load_draft_model(db_path, draft_id)
    dramaturgy = next((d for d in model.dramaturgies if d.id == dramaturgy_id), None)
    if dramaturgy is None:
        raise ValueError(f"作品が見つかりません: {dramaturgy_id}")
    agent = _agent(project, dramaturgy, step)
    handler = _HANDLERS[step.key]

    history = ai_build_store.list_messages(db_path, dramaturgy_id, step.key, scene_id)
    generator = build_task_text_generator(project, step.task_code, TextConfig(max_output_tokens=MAX_OUTPUT_TOKENS))
    attachments = [
        Attachment.from_file(r.path, r.media_type)
        for r in references
        if generator.accepts_attachment(r.media_type)
    ]
    reference_text = _reference_text(references, generator)

    request = _request_text(handler.context(project, model, dramaturgy, scene_id), reference_text, mode, text)
    messages = [*_history_messages(step.key, history), Message(role="user", text=request)]
    reply = generator.generate_structured(
        messages,
        handler.schema,
        system_instruction=handler.prompt(agent, step.task_code, mode),
        attachments=attachments,
    )
    content = _draft_content(db_path, draft_id)
    outcome = handler.patch(project, content, dramaturgy, scene_id, step.task_code, reply, mode)
    stored_reply: dict[str, Any] = {
        "proposal": (outcome.shown or handler.display(reply)) if outcome.patch else None,
        "changed_fields": outcome.changes,
        "evidence": [e.model_dump() for e in reply.evidence],
        "questions": [q for q in reply.questions if q.strip()],
        "warnings": [w for w in reply.warnings if w.strip()] + outcome.warnings,
    }
    return ai_build_store.add_exchange(
        db_path,
        dramaturgy_id,
        step.key,
        scene_id,
        mode.value,
        text,
        [r.file_id for r in references],
        reply.message.strip(),
        stored_reply,
        yaml.safe_dump(outcome.patch, allow_unicode=True, sort_keys=False) if outcome.patch else None,
    )


def apply_message(project: Project, draft_id: str, message_id: int) -> StoredMessage:
    """生成AIの提案を、編集用の下書きに重ねる(Apply)。"""
    db_path = project.layout.project_db_path
    message = ai_build_store.get_message(db_path, message_id)
    if message.proposal_status != PENDING or not message.patch_yaml:
        raise ValueError("反映できる提案ではありません(反映済み・取り消し済み・提案なし)。")
    revision = drama_draft_editor.apply_to_draft(db_path, draft_id, message.patch_yaml)
    return ai_build_store.set_proposal_status(db_path, message_id, APPLIED, revision)


def undo_message(project: Project, draft_id: str, message_id: int) -> StoredMessage:
    """反映した提案を取り消す(下書きの最後の変更がその提案の反映であるときだけ)。"""
    db_path = project.layout.project_db_path
    message = ai_build_store.get_message(db_path, message_id)
    if message.proposal_status != APPLIED:
        raise ValueError("取り消せるのは、反映した提案だけです。")
    revisions = drama_draft_editor.list_revisions(db_path, draft_id)
    if not revisions or revisions[-1].revision != message.applied_revision:
        raise ValueError(
            "この提案を反映した後に、下書きに別の変更があります。Undoは下書きの最後の変更だけを戻せます。"
        )
    drama_draft_editor.undo(db_path, draft_id)
    return ai_build_store.set_proposal_status(db_path, message_id, UNDONE, None)


def list_messages(
    project: Project, dramaturgy_id: str, step_key: str, scene_id: Optional[str] = None
) -> list[StoredMessage]:
    scene_id = _scene_id(find_step(step_key), scene_id)
    return ai_build_store.list_messages(project.layout.project_db_path, dramaturgy_id, step_key, scene_id)


def clear_messages(project: Project, dramaturgy_id: str, step_key: str, scene_id: Optional[str] = None) -> int:
    scene_id = _scene_id(find_step(step_key), scene_id)
    return ai_build_store.clear_messages(project.layout.project_db_path, dramaturgy_id, step_key, scene_id)


def _scene_id(step: BuildStep, scene_id: Optional[str]) -> Optional[str]:
    """工程の対象のシーン(シーンごとの工程では必須、ほかの工程ではNone)。"""
    if not step.per_scene:
        return None
    if not scene_id:
        raise ValueError(f"工程 '{step.label}' はシーンを選んでください。")
    return scene_id


# ---------------------------------------------------------------------------


def _agent(project: Project, dramaturgy: Dramaturgy, step: BuildStep) -> BaseAgent:
    """工程の相談相手(作品のエージェント。いなければプロジェクトのユーザー既定から作る)。"""
    return role_agent(project, dramaturgy, step.role_name)


def role_agent(project: Project, dramaturgy: Dramaturgy, role_name: str) -> BaseAgent:
    """職能(モデル定義YAMLの区画名の単数形)のエージェント。作品にいればそれ、いなければプロジェクトのユーザー既定から作る。"""
    agent_class = AGENT_ROLES[role_name]
    agent = next((a for a in dramaturgy.agents if isinstance(a, agent_class)), None)
    if agent is not None:
        return agent
    spec = agent_default_store.read_user_default(project.layout, role_name)
    text = yaml.safe_dump(
        {
            "dramaturgy": {
                "title": "-",
                "agents": {f"{role_name}s": [spec.model_dump(exclude_none=True)]},
            }
        },
        allow_unicode=True,
    )
    return build_model_definition_from_yaml(text).dramaturgy.agents[0]


def _reference_text(references: list[ReferenceFile], generator: TextGenerator) -> str:
    """添付できない資料のテキスト(資料ごとに見出しを付ける)。"""
    parts = []
    for reference in references:
        if generator.accepts_attachment(reference.media_type):
            parts.append(f"## {reference.filename}\n(添付したファイル)")
            continue
        try:
            with open(reference.path, "rb") as f:
                text = document_text(f.read(), reference.file_format)
        except Exception as exc:  # 壊れた・読めない形式のファイル(生成AIの失敗と区別する)
            raise ValueError(
                f"資料「{reference.filename}」を読めません: {type(exc).__name__}: {exc}"
            ) from exc
        parts.append(f"## {reference.filename}\n{text}")
    return "\n\n".join(parts)


def _request_text(context: str, reference_text: str, mode: BuildMode, text: str) -> str:
    parts = [context]
    if reference_text:
        parts.append(f"# 参照する資料\n{reference_text}")
    label = "ワンショット下書きの要望" if mode is BuildMode.ONE_SHOT else "利用者の発言"
    parts.append(f"# {label}\n{text or '(特に無し。今の内容と資料から作る)'}")
    return "\n\n".join(parts)


def _history_messages(step_key: str, history: list[StoredMessage]) -> list[Message]:
    """今の工程の会話の履歴(生成AIの発言には、そのとき提案した内容を添える)。"""
    messages = []
    for item in history:
        if item.role == "user":
            messages.append(Message(role="user", text=item.text or "(要望なし)"))
            continue
        text = item.text
        reply = item.reply or {}
        if reply.get("proposal"):
            if step_key == "proposal":
                summary = proposal_prompts.proposal_summary(
                    proposal_prompts.ProposalDraft.model_validate(reply["proposal"])
                )
            elif step_key == "synopsis":
                summary = synopsis_prompts.synopsis_summary(reply["proposal"])
            elif step_key == "scenes":
                summary = scene_synopsis_prompts.scene_synopsis_summary(reply["proposal"])
            elif step_key == "script":
                summary = script_prompts.script_summary(reply["proposal"])
            elif step_key == "direction":
                summary = direction_prompts.direction_summary(reply["proposal"])
            else:
                summary = "\n".join(f"* {c}" for c in reply.get("changed_fields") or [])
            text = f"{text}\n\n[提案した内容]\n{summary}"
        messages.append(Message(role="assistant", text=text))
    return messages


def _draft_content(db_path: str, draft_id: str) -> dict[str, Any]:
    """下書きの中身(id・key付きのモデル定義YAMLの対応表)。"""
    documents = load_documents(drama_draft_editor.draft_yaml(db_path, draft_id))
    return documents[0] if documents else {}


class _StepHandler:
    """工程ごとの、応答の型・指示・今の内容・提案の部分YAMLの作り方・提案の表示。"""

    def __init__(self, schema, prompt, context, patch, display):
        self.schema = schema
        self.prompt = prompt  # (agent, task_code, mode) -> Prompt
        self.context = context  # (project, model, dramaturgy, scene_id) -> str
        self.patch = patch  # (project, content, dramaturgy, scene_id, task_code, reply, mode) -> PatchOutcome
        self.display = display  # (reply) -> 画面に出す提案の対応表


def _world_patch(project, content, dramaturgy, scene_id, task_code, reply, mode) -> PatchOutcome:
    if mode is BuildMode.DIALOGUE and not reply.has_proposal:
        return PatchOutcome(None, [], [])
    return world_patch(
        content,
        dramaturgy.id,
        task_code,
        getattr(reply, "characters", []),
        getattr(reply, "groups", []),
        getattr(reply, "relationships", []),
    )


def _world_display(reply) -> dict[str, Any]:
    keys = ("characters", "groups", "relationships")
    return {key: [item.model_dump() for item in getattr(reply, key)] for key in keys if hasattr(reply, key)}


def _world_handler(task_code: str) -> _StepHandler:
    return _StepHandler(
        world_prompts.REPLIES[task_code],
        world_prompts.world_prompt,
        lambda project, model, dramaturgy, scene_id: world_prompts.world_context(model, dramaturgy),
        _world_patch,
        _world_display,
    )


_HANDLERS: dict[str, _StepHandler] = {
    "proposal": _StepHandler(
        proposal_prompts.ProposalReply,
        lambda agent, code, mode: proposal_prompts.proposal_prompt(agent, mode),
        lambda project, model, dramaturgy, scene_id: proposal_prompts.proposal_context(dramaturgy.proposal, dramaturgy.input_language),
        lambda project, content, dramaturgy, scene_id, code, reply, mode: proposal_patch(dramaturgy, reply, mode),
        lambda reply: reply.proposal.model_dump(),
    ),
    "characters": _world_handler(world_prompts.CHARACTERS_TASK),
    "groups": _world_handler(world_prompts.GROUPS_TASK),
    "relationships": _world_handler(world_prompts.RELATIONSHIPS_TASK),
    "synopsis": _StepHandler(
        synopsis_prompts.SynopsisReply,
        lambda agent, code, mode: synopsis_prompts.synopsis_prompt(agent, mode),
        lambda project, model, dramaturgy, scene_id: synopsis_prompts.synopsis_context(dramaturgy),
        lambda project, content, dramaturgy, scene_id, code, reply, mode: (
            PatchOutcome(None, [], [])
            if mode is BuildMode.DIALOGUE and not reply.has_proposal
            else synopsis_patch(dramaturgy, reply)
        ),
        lambda reply: {"synopsis": reply.synopsis, "acts": [a.model_dump() for a in reply.acts]},
    ),
    "scenes": _StepHandler(
        scene_synopsis_prompts.SceneSynopsisReply,
        lambda agent, code, mode: scene_synopsis_prompts.scene_synopsis_prompt(agent, mode),
        lambda project, model, dramaturgy, scene_id: scene_synopsis_prompts.scene_synopsis_context(dramaturgy),
        lambda project, content, dramaturgy, scene_id, code, reply, mode: (
            PatchOutcome(None, [], [])
            if mode is BuildMode.DIALOGUE and not reply.has_proposal
            else scene_synopsis_patch(dramaturgy, reply)
        ),
        lambda reply: {"scenes": [s.model_dump() for s in reply.scenes]},
    ),
    "casting": _StepHandler(
        casting_prompts.CastingReply,
        casting_prompts.casting_prompt,
        lambda project, model, dramaturgy, scene_id: casting_prompts.casting_context(model, dramaturgy),
        lambda project, content, dramaturgy, scene_id, code, reply, mode: (
            PatchOutcome(None, [], [])
            if mode is BuildMode.DIALOGUE and not reply.has_proposal
            else cast_patch(content, dramaturgy.id, reply.casts)
        ),
        lambda reply: {"casts": [c.model_dump() for c in reply.casts]},
    ),
    "audition": _StepHandler(
        casting_prompts.AuditionReply,
        casting_prompts.casting_prompt,
        lambda project, model, dramaturgy, scene_id: casting_prompts.audition_context(
            dramaturgy, _audition_voices(project, dramaturgy), _audition_language(dramaturgy)
        ),
        lambda project, content, dramaturgy, scene_id, code, reply, mode: (
            PatchOutcome(None, [], [])
            if mode is BuildMode.DIALOGUE and not reply.has_proposal
            else audition_patch(
                content,
                dramaturgy.id,
                reply.auditions,
                _audition_voices(project, dramaturgy),
                project.tts.client,
                project.tts.model,
            )
        ),
        lambda reply: {"auditions": [a.model_dump() for a in reply.auditions]},
    ),
    "script": _StepHandler(
        script_prompts.ScriptReply,
        lambda agent, code, mode: script_prompts.script_prompt(agent, mode),
        lambda project, model, dramaturgy, scene_id: script_prompts.script_context(dramaturgy, scene_id),
        lambda project, content, dramaturgy, scene_id, code, reply, mode: (
            PatchOutcome(None, [], [])
            if mode is BuildMode.DIALOGUE and not reply.has_proposal
            else script_patch(content, dramaturgy.id, scene_id, reply.lines)
        ),
        lambda reply: {"lines": [line.model_dump() for line in reply.lines]},
    ),
    "direction": _StepHandler(
        direction_prompts.DirectionReply,
        lambda agent, code, mode: direction_prompts.direction_prompt(agent, mode),
        lambda project, model, dramaturgy, scene_id: direction_prompts.direction_context(dramaturgy, scene_id),
        lambda project, content, dramaturgy, scene_id, code, reply, mode: (
            PatchOutcome(None, [], [])
            if mode is BuildMode.DIALOGUE and not reply.has_proposal
            else direction_patch(content, dramaturgy.id, scene_id, reply.dialogues)
        ),
        lambda reply: {"dialogues": [d.model_dump() for d in reply.dialogues]},
    ),
}


def _audition_language(dramaturgy: Dramaturgy) -> str:
    """Auditionで声を選ぶ言語(作品の音声にする言語。無ければ制作に使う言語)。"""
    language = dramaturgy.output_language or dramaturgy.input_language
    if not language:
        raise ValueError("作品の言語(Output Language)を、Dramaturgy EditorのPropertiesタブで設定してください。")
    return language


def _audition_voices(project: Project, dramaturgy: Dramaturgy):
    """Auditionで選べる声(プロジェクトの音声合成の提供元の、作品の言語の声)。"""
    return voice_catalog.list_voices(project, _audition_language(dramaturgy))
