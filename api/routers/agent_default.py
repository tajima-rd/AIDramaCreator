# api/routers/agent_default.py
"""エージェントのユーザー既定のエンドポイント(プロジェクトごと。core.service.api.agent_default)。"""

from fastapi import APIRouter, Request

from api.routers._http import _bad_request
from api.yaml_io import parse_yaml_body, yaml_response
from core.schema.formats.dramaturgy_definition import AgentSpec
from core.service.api import agent_default as agent_default_api

router = APIRouter()


@router.get("/projects/{project_id}/agent-defaults")
async def list_agent_defaults(project_id: str):
    return yaml_response(agent_default_api.list_agent_defaults(project_id))


@router.put("/projects/{project_id}/agent-defaults/{role_name}")
async def save_agent_default(project_id: str, role_name: str, request: Request):
    """本文はエージェント(モデル定義YAMLの1人分。省略した項目はシステム既定)。"""
    body = await parse_yaml_body(request, AgentSpec)
    try:
        return yaml_response(agent_default_api.save_agent_default(project_id, role_name, body))
    except ValueError as exc:
        raise _bad_request(exc) from exc


@router.post("/projects/{project_id}/agent-defaults/{role_name}/restore")
async def restore_system_default(project_id: str, role_name: str):
    try:
        return yaml_response(agent_default_api.restore_system_default(project_id, role_name))
    except ValueError as exc:
        raise _bad_request(exc) from exc
