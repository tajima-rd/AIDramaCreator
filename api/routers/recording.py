# api/routers/recording.py
"""
音声の生成のエンドポイント(core.service.api.recording。Dramaturgy EditorのRecordingタブ)。
生成は台詞ごとに音声合成を呼ぶので数十秒〜数分かかる(スレッドで動かす)。入力の誤り・足りないもの・音声合成の未設定は400、
音声が無ければ404、音声合成の呼び出しの失敗は502。プロジェクト・下書きの不在はapi/main.pyの共通の例外ハンドラが404にする。
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from api.routers._http import _bad_request, _not_found
from api.yaml_io import parse_yaml_body, yaml_response
from core.infra.store.drama_version_store import DraftNotFoundError
from core.infra.store.recording_store import MEDIA_TYPE
from core.project.project import ProjectNotFoundError
from core.schema.api.recording import RecordingCreateRequest
from core.service.api import recording as recording_api

router = APIRouter()


@router.get("/projects/{project_id}/recordings")
async def list_recordings(project_id: str, draft_id: str, dramaturgy_id: str, language: str = ""):
    try:
        return yaml_response(recording_api.list_recordings(project_id, draft_id, dramaturgy_id, language))
    except ValueError as exc:
        raise _bad_request(exc) from exc


@router.post("/projects/{project_id}/recordings")
async def record_scene(project_id: str, request: Request):
    body = await parse_yaml_body(request, RecordingCreateRequest)
    try:
        return yaml_response(await run_in_threadpool(recording_api.record_scene, project_id, body))
    except (ProjectNotFoundError, DraftNotFoundError):
        raise
    except ValueError as exc:
        raise _bad_request(exc) from exc
    except Exception as exc:  # 接続・認証・応答の誤り等、音声合成の呼び出しの失敗
        raise HTTPException(
            status_code=502, detail=f"音声を作れませんでした: {type(exc).__name__}: {exc}"
        ) from exc


@router.get("/projects/{project_id}/recordings/{dramaturgy_id}/{language}/{scene_id}.mp3")
async def recording_file(project_id: str, dramaturgy_id: str, language: str, scene_id: str):
    """音声のファイルそのもの(YAMLではない)。ブラウザで再生できるようinlineで返す。"""
    try:
        path = recording_api.recording_file(project_id, dramaturgy_id, language, scene_id)
    except KeyError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _bad_request(exc) from exc
    return FileResponse(path, media_type=MEDIA_TYPE, filename=f"{scene_id}.mp3", content_disposition_type="inline")
