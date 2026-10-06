# api/routers/ai_build.py
"""
Build with AIのエンドポイント(core.service.api.ai_build)。発言の送信は生成AIを呼ぶので数秒〜数分かかる(スレッドで動かす)。
入力・状態の誤りと生成AIの未設定は400、発言が無ければ404、生成AIの呼び出しの失敗は502(発言は記録しない)。
プロジェクト・下書き・資料の不在はapi/main.pyの共通の例外ハンドラが404にする。
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from api.routers._http import _bad_request, _not_found
from api.yaml_io import parse_yaml_body, yaml_response
from core.infra.store.drama_version_store import DraftNotFoundError
from core.project.dataset import DatasetNotFoundError
from core.project.project import ProjectNotFoundError
from core.schema import AiBuildProposalActionRequest, AiBuildSendRequest
from core.service.api import ai_build as ai_build_api

router = APIRouter()


def _call(fn, *args):
    try:
        return yaml_response(fn(*args))
    except KeyError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _bad_request(exc) from exc


@router.get("/projects/{project_id}/ai-build/steps")
async def list_steps(project_id: str):
    return yaml_response(ai_build_api.list_steps(project_id))


@router.get("/projects/{project_id}/ai-build/{step}/messages")
async def list_messages(project_id: str, step: str, dramaturgy_id: str, scene_id: Optional[str] = None):
    return _call(ai_build_api.list_messages, project_id, step, dramaturgy_id, scene_id)


@router.post("/projects/{project_id}/ai-build/{step}/messages")
async def send_message(project_id: str, step: str, request: Request):
    body = await parse_yaml_body(request, AiBuildSendRequest)
    try:
        return yaml_response(
            await run_in_threadpool(ai_build_api.send_message, project_id, step, body)
        )
    except (ProjectNotFoundError, DraftNotFoundError, DatasetNotFoundError):
        raise
    except (KeyError, ValueError) as exc:
        raise _bad_request(exc) from exc
    except Exception as exc:  # 接続・認証・応答の形の誤り等、生成AIの呼び出しの失敗
        raise HTTPException(
            status_code=502, detail=f"生成AIの呼び出しに失敗しました: {type(exc).__name__}: {exc}"
        ) from exc


@router.delete("/projects/{project_id}/ai-build/{step}/messages")
async def clear_messages(project_id: str, step: str, dramaturgy_id: str, scene_id: Optional[str] = None):
    return _call(ai_build_api.clear_messages, project_id, step, dramaturgy_id, scene_id)


@router.post("/projects/{project_id}/ai-build/messages/{message_id}/apply")
async def apply_proposal(project_id: str, message_id: int, request: Request):
    body = await parse_yaml_body(request, AiBuildProposalActionRequest)
    return _call(ai_build_api.apply_proposal, project_id, message_id, body)


@router.post("/projects/{project_id}/ai-build/messages/{message_id}/undo")
async def undo_proposal(project_id: str, message_id: int, request: Request):
    body = await parse_yaml_body(request, AiBuildProposalActionRequest)
    return _call(ai_build_api.undo_proposal, project_id, message_id, body)
