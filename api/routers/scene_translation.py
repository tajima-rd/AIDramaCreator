# api/routers/scene_translation.py
"""
シーンの台詞の翻訳のエンドポイント(core.service.api.scene_translation)。生成AIを呼ぶので数秒〜数分かかる(スレッドで動かす)。
入力の誤り・訳さない作品・生成AIの未設定は400、生成AIの呼び出しの失敗は502。プロジェクト・下書きの不在はapi/main.pyの共通の
例外ハンドラが404にする。
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from api.routers._http import _bad_request
from api.yaml_io import parse_yaml_body, yaml_response
from core.infra.store.drama_version_store import DraftNotFoundError
from core.project.project import ProjectNotFoundError
from core.schema.api.scene_translation import SceneTranslationRequest
from core.service.api import scene_translation as scene_translation_api

router = APIRouter()


@router.post("/projects/{project_id}/drama-drafts/{draft_id}/scene-translation")
async def translate_scene(project_id: str, draft_id: str, request: Request):
    body = await parse_yaml_body(request, SceneTranslationRequest)
    try:
        return yaml_response(
            await run_in_threadpool(scene_translation_api.translate_scene, project_id, draft_id, body)
        )
    except (ProjectNotFoundError, DraftNotFoundError):
        raise
    except ValueError as exc:
        raise _bad_request(exc) from exc
    except Exception as exc:  # 接続・認証・応答の形の誤り等、生成AIの呼び出しの失敗
        raise HTTPException(
            status_code=502, detail=f"生成AIの呼び出しに失敗しました: {type(exc).__name__}: {exc}"
        ) from exc
