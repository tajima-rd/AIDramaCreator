# api/routers/drama_draft.py
"""
作品モデルの下書きのエンドポイント(core.service.api.drama_draft)。Apply・直接編集・取り込みは、本文の部分YAMLを
そのまま渡す。YAMLの形・参照の誤りとopenでない下書きの変更は400、元にした版が古い確定は409。下書き・版の不在は
api/main.pyの共通の例外ハンドラが404にする。
"""

from typing import Optional

import yaml
from fastapi import APIRouter, HTTPException, Request

from api.routers._http import _bad_request
from api.yaml_io import parse_yaml_body, read_text_body, yaml_response
from core.schema import (
    DramaDraftConfirmRequest,
    DramaDraftCreateRequest,
    DramaDraftImportPathRequest,
)
from core.service.api import drama_draft as drama_draft_api

router = APIRouter()

_INVALID = (ValueError, KeyError, yaml.YAMLError)


@router.post("/projects/{project_id}/drama-drafts")
async def create_draft(project_id: str, request: Request):
    body = await parse_yaml_body(request, DramaDraftCreateRequest)
    return yaml_response(drama_draft_api.create_draft(project_id, body))


@router.get("/projects/{project_id}/drama-drafts")
async def list_drafts(project_id: str, status: Optional[str] = None):
    return yaml_response(drama_draft_api.list_drafts(project_id, status))


@router.get("/projects/{project_id}/drama-drafts/{draft_id}")
async def get_draft(project_id: str, draft_id: str):
    return yaml_response(drama_draft_api.get_draft(project_id, draft_id))


@router.get("/projects/{project_id}/drama-drafts/{draft_id}/content")
async def get_draft_content(project_id: str, draft_id: str, revision: Optional[int] = None):
    content = drama_draft_api.get_draft_content(project_id, draft_id, revision)
    return yaml_response(content, exclude_unset=True)


@router.get("/projects/{project_id}/drama-drafts/{draft_id}/revisions")
async def list_revisions(project_id: str, draft_id: str):
    return yaml_response(drama_draft_api.list_revisions(project_id, draft_id))


@router.post("/projects/{project_id}/drama-drafts/{draft_id}/apply")
async def apply_proposal(project_id: str, draft_id: str, request: Request):
    text = await read_text_body(request)
    try:
        return yaml_response(drama_draft_api.apply_proposal(project_id, draft_id, text))
    except _INVALID as exc:
        raise _bad_request(exc) from exc


@router.post("/projects/{project_id}/drama-drafts/{draft_id}/edit")
async def edit_draft(project_id: str, draft_id: str, request: Request):
    text = await read_text_body(request)
    try:
        return yaml_response(drama_draft_api.edit_draft(project_id, draft_id, text))
    except _INVALID as exc:
        raise _bad_request(exc) from exc


@router.post("/projects/{project_id}/drama-drafts/{draft_id}/import")
async def import_yaml(project_id: str, draft_id: str, request: Request, replace: bool = False):
    text = await read_text_body(request)
    try:
        return yaml_response(drama_draft_api.import_yaml(project_id, draft_id, text, replace))
    except _INVALID as exc:
        raise _bad_request(exc) from exc


@router.post("/projects/{project_id}/drama-drafts/{draft_id}/import-path")
async def import_path(project_id: str, draft_id: str, request: Request):
    body = await parse_yaml_body(request, DramaDraftImportPathRequest)
    try:
        return yaml_response(drama_draft_api.import_path(project_id, draft_id, body))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except _INVALID as exc:
        raise _bad_request(exc) from exc


@router.post("/projects/{project_id}/drama-drafts/{draft_id}/undo")
async def undo(project_id: str, draft_id: str):
    try:
        return yaml_response(drama_draft_api.undo(project_id, draft_id))
    except ValueError as exc:
        raise _bad_request(exc) from exc


@router.post("/projects/{project_id}/drama-drafts/{draft_id}/confirm")
async def confirm_draft(project_id: str, draft_id: str, request: Request):
    body = await parse_yaml_body(request, DramaDraftConfirmRequest)
    try:
        return yaml_response(drama_draft_api.confirm_draft(project_id, draft_id, body))
    except drama_draft_api.DraftConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise _bad_request(exc) from exc


@router.post("/projects/{project_id}/drama-drafts/{draft_id}/discard")
async def discard_draft(project_id: str, draft_id: str):
    try:
        return yaml_response(drama_draft_api.discard_draft(project_id, draft_id))
    except ValueError as exc:
        raise _bad_request(exc) from exc
