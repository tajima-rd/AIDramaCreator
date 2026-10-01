# api/routers/drama_model.py
"""作品モデルの正本と版のエンドポイント(読むだけ。core.service.api.drama_model)。"""

from fastapi import APIRouter

from api.yaml_io import yaml_response
from core.service.api import drama_model as drama_model_api

router = APIRouter()


@router.get("/projects/{project_id}/drama-model")
async def get_model(project_id: str):
    return yaml_response(drama_model_api.get_model(project_id), exclude_unset=True)


@router.get("/projects/{project_id}/drama-model/versions")
async def list_versions(project_id: str):
    return yaml_response(drama_model_api.list_versions(project_id))


@router.get("/projects/{project_id}/drama-model/versions/{version}")
async def get_version(project_id: str, version: int):
    return yaml_response(drama_model_api.get_version(project_id, version), exclude_unset=True)
