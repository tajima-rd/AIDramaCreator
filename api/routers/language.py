# api/routers/language.py
"""作品の言語の一覧のエンドポイント(core.service.api.language)。"""

from fastapi import APIRouter

from api.yaml_io import yaml_response
from core.service.api import language as language_api

router = APIRouter()


@router.get("/languages")
async def list_languages():
    return yaml_response(language_api.list_languages())
