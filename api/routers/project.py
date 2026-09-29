# api/routers/project.py
"""プロジェクト(Project/Connectionメニュー)のエンドポイント(docs/status.md参照)。"""

from fastapi import APIRouter, HTTPException, Request

from api.yaml_io import parse_yaml_body, yaml_response
from core.schema import (
    ProjectCreateRequest,
    ProjectOpenRequest,
    ProjectPropertiesUpdateRequest,
    ProjectSaveAsRequest,
    ProjectUpdatePathRequest,
)
from core.service.api import project as project_api

router = APIRouter()


@router.post("/projects")
async def create_project(request: Request):
    body = await parse_yaml_body(request, ProjectCreateRequest)
    try:
        return yaml_response(project_api.create_project(body))
    except FileExistsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/projects/open")
async def open_project(request: Request):
    body = await parse_yaml_body(request, ProjectOpenRequest)
    try:
        return yaml_response(project_api.open_project(body))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/projects")
async def list_projects():
    return yaml_response(project_api.list_projects())


@router.get("/projects/{project_id}")
async def get_project(project_id: str):
    return yaml_response(project_api.get_project(project_id))


@router.put("/projects/{project_id}")
async def update_project_properties(project_id: str, request: Request):
    body = await parse_yaml_body(request, ProjectPropertiesUpdateRequest)
    return yaml_response(project_api.update_project_properties(project_id, body))


@router.put("/projects/{project_id}/path")
async def update_project_path(project_id: str, request: Request):
    body = await parse_yaml_body(request, ProjectUpdatePathRequest)
    try:
        return yaml_response(project_api.update_project_path(project_id, body))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/projects/{project_id}/save")
async def save_project(project_id: str):
    return yaml_response(project_api.save_project(project_id))


@router.post("/projects/{project_id}/save-as")
async def save_project_as(project_id: str, request: Request):
    body = await parse_yaml_body(request, ProjectSaveAsRequest)
    try:
        return yaml_response(project_api.save_project_as(project_id, body))
    except FileExistsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
