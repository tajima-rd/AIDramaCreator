# core/service/api/ai_build.py
"""
Build with AIの公開API(docs/architecture.md 10節)。生成AIの提案はApplyするまで作品に入らず、Applyは編集用の下書きに重ねる
(確定はSave Version)。

エラーは例外で返す: project_idが未登録ならProjectNotFoundError、下書きが無ければDraftNotFoundError、資料が無ければ
DatasetNotFoundError、発言が無ければKeyError、工程・作品・入力・状態の誤りと生成AIの未設定はValueError。生成AIの呼び出しの
失敗はその例外のまま。
"""

from core.infra.store.ai_build_store import StoredMessage
from core.infra.store.project_file_store import read_project
from core.infra.store.project_registry_store import resolve_layout
from core.project.dataset import file_format
from core.project.project import Project
from core.prompt.ai_build.common import BuildMode
from core.prompt.ai_build.step import BUILD_STEPS
from core.schema import (
    AiBuildClearResult,
    AiBuildMessageInfo,
    AiBuildMessageListResult,
    AiBuildProposalActionRequest,
    AiBuildSendRequest,
    AiBuildStepInfo,
    AiBuildStepListResult,
)
from core.service.api import dataset as dataset_api
from core.service.process.genai import ai_builder


def _project(project_id: str) -> Project:
    return read_project(resolve_layout(project_id).root_dir)


def _info(message: StoredMessage) -> AiBuildMessageInfo:
    reply = message.reply or {}
    return AiBuildMessageInfo(
        id=message.id,
        step=message.step,
        role=message.role,
        mode=message.mode,
        text=message.text,
        proposal=reply.get("proposal"),
        changed_fields=reply.get("changed_fields") or [],
        evidence=reply.get("evidence") or [],
        questions=reply.get("questions") or [],
        warnings=reply.get("warnings") or [],
        proposal_status=message.proposal_status,
        reference_file_ids=message.reference_file_ids,
        created_at=message.created_at,
    )


def list_steps(project_id: str) -> AiBuildStepListResult:
    resolve_layout(project_id)
    return AiBuildStepListResult(
        steps=[
            AiBuildStepInfo(
                key=s.key,
                label=s.label,
                role_name=s.role_name,
                task_code=s.task_code,
                available=s.available,
            )
            for s in BUILD_STEPS
        ]
    )


def list_messages(project_id: str, step: str, dramaturgy_id: str) -> AiBuildMessageListResult:
    messages = ai_builder.list_messages(_project(project_id), dramaturgy_id, step)
    return AiBuildMessageListResult(messages=[_info(m) for m in messages])


def send_message(project_id: str, step: str, request: AiBuildSendRequest) -> AiBuildMessageInfo:
    """発言を生成AIに送り、返事(と提案)を返す。下書きは変えない。"""
    project = _project(project_id)
    references = []
    for file_id in request.reference_file_ids:
        location = dataset_api.get_dataset_file(project_id, file_id)
        references.append(
            ai_builder.ReferenceFile(
                file_id,
                location.filename,
                location.path,
                file_format(location.filename),
                location.media_type,
            )
        )
    message = ai_builder.send_message(
        project,
        request.draft_id,
        request.dramaturgy_id,
        step,
        BuildMode(request.mode),
        request.text,
        references,
    )
    return _info(message)


def apply_proposal(
    project_id: str, message_id: int, request: AiBuildProposalActionRequest
) -> AiBuildMessageInfo:
    return _info(ai_builder.apply_message(_project(project_id), request.draft_id, message_id))


def undo_proposal(
    project_id: str, message_id: int, request: AiBuildProposalActionRequest
) -> AiBuildMessageInfo:
    return _info(ai_builder.undo_message(_project(project_id), request.draft_id, message_id))


def clear_messages(project_id: str, step: str, dramaturgy_id: str) -> AiBuildClearResult:
    return AiBuildClearResult(
        deleted=ai_builder.clear_messages(_project(project_id), dramaturgy_id, step)
    )
