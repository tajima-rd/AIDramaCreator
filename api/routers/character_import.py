# api/routers/character_import.py
"""
企画書の登場人物の取り込みのエンドポイント(core.service.api.character_import)。生成AIを呼ぶので数秒〜数十秒かかる
(スレッドで動かす)。入力・状態の誤りと作業補助の生成AIの未設定は400、生成AIの呼び出しの失敗は502。
下書き・プロジェクトの不在はapi/main.pyの共通の例外ハンドラが404にする。
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from api.routers._http import _bad_request
from api.yaml_io import parse_yaml_body, yaml_response
from core.infra.store.drama_version_store import DraftNotFoundError
from core.project.project import ProjectNotFoundError
from core.schema import CharacterConflictCheckRequest, CharacterImportRequest
from core.service.api import character_import as character_import_api

router = APIRouter()


async def _run(fn, *args):
    try:
        return yaml_response(await run_in_threadpool(fn, *args))
    except (ProjectNotFoundError, DraftNotFoundError):
        raise
    except (KeyError, ValueError) as exc:
        raise _bad_request(exc) from exc
    except Exception as exc:  # 接続・認証・応答の形の誤り等、生成AIの呼び出しの失敗
        raise HTTPException(status_code=502, detail=f"生成AIの呼び出しに失敗しました: {type(exc).__name__}: {exc}") from exc


@router.post("/projects/{project_id}/drama-drafts/{draft_id}/character-import/check")
async def check_conflict(project_id: str, draft_id: str, request: Request):
    body = await parse_yaml_body(request, CharacterConflictCheckRequest)
    return await _run(character_import_api.check_conflict, project_id, draft_id, body)


@router.post("/projects/{project_id}/drama-drafts/{draft_id}/character-import")
async def import_character(project_id: str, draft_id: str, request: Request):
    body = await parse_yaml_body(request, CharacterImportRequest)
    return await _run(character_import_api.import_character, project_id, draft_id, body)
