# api/routers/preference.py
"""プロジェクトの設定(Project > Preferences)のエンドポイント(docs/status.md参照)。

モデル名の一覧・接続先URLの候補・APIキーの状態と保存は、プロジェクトに属さない(キーは
~/.aidc/secrets.envに、提供元と接続先ごとに保存する)ため/preferences/配下に置く。生成AIやサーバーへの問い合わせ(数秒かかることがある)は、
他のリクエストを止めないようスレッドで実行する。
"""

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from api.yaml_io import parse_yaml_body, yaml_response
from core.schema import (
    ApiKeyUpdateRequest,
    EmbeddingConnectionTestRequest,
    LlmConnectionTestRequest,
    ModelListRequest,
    PreferenceUpdateRequest,
)
from core.service.api import preference as preference_api

router = APIRouter()


@router.get("/projects/{project_id}/preferences")
async def get_preferences(project_id: str):
    return yaml_response(preference_api.get_preferences(project_id))


@router.put("/projects/{project_id}/preferences")
async def update_preferences(project_id: str, request: Request):
    body = await parse_yaml_body(request, PreferenceUpdateRequest)
    try:
        return yaml_response(preference_api.update_preferences(project_id, body))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/projects/{project_id}/preferences/llm-test")
async def test_llm_connection(project_id: str, request: Request):
    body = await parse_yaml_body(request, LlmConnectionTestRequest)
    try:
        return yaml_response(await run_in_threadpool(preference_api.test_llm_connection, project_id, body))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/projects/{project_id}/preferences/embedding-test")
async def test_embedding_connection(project_id: str, request: Request):
    body = await parse_yaml_body(request, EmbeddingConnectionTestRequest)
    try:
        return yaml_response(await run_in_threadpool(preference_api.test_embedding_connection, project_id, body))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/preferences/models")
async def list_models(request: Request):
    body = await parse_yaml_body(request, ModelListRequest)
    try:
        return yaml_response(await run_in_threadpool(preference_api.list_models, body))
    except Exception as exc:  # 接続できない・認証の失敗・キーが無い等、理由をそのまま利用者に見せる
        raise HTTPException(status_code=400, detail=f"モデルの一覧を取得できませんでした: {exc}") from exc


@router.get("/preferences/api-url-candidates")
async def list_api_url_candidates(client: str):
    return yaml_response(await run_in_threadpool(preference_api.list_api_url_candidates, client))


@router.get("/preferences/api-key")
async def get_api_key(client: str, api_url: str | None = None):
    return yaml_response(preference_api.get_api_key(client, api_url))


@router.put("/preferences/api-key")
async def update_api_key(request: Request):
    body = await parse_yaml_body(request, ApiKeyUpdateRequest)
    try:
        return yaml_response(preference_api.update_api_key(body))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
