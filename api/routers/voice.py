# api/routers/voice.py
"""
音声合成の声(話者)の一覧のエンドポイント(core.service.api.voice)。
設定・APIキーの不足は400、提供元の呼び出しの失敗は502。
"""

from typing import Optional

from fastapi import APIRouter, HTTPException

from api.routers._http import _bad_request
from api.yaml_io import yaml_response
from core.project.project import ProjectNotFoundError
from core.service.api import voice as voice_api

router = APIRouter()


@router.get("/projects/{project_id}/voices")
async def list_voices(project_id: str, language: Optional[str] = None):
    try:
        return yaml_response(voice_api.list_voices(project_id, language))
    except ProjectNotFoundError:
        raise
    except ValueError as exc:
        raise _bad_request(exc) from exc
    except Exception as exc:  # 接続・認証の誤り等、提供元の呼び出しの失敗
        raise HTTPException(
            status_code=502, detail=f"声の一覧を取得できませんでした: {type(exc).__name__}: {exc}"
        ) from exc
