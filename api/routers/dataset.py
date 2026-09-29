# api/routers/dataset.py
"""Datasetのエンドポイント(docs/status.md参照)。"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from api.yaml_io import parse_yaml_body, yaml_response
from core.schema import (
    DatasetFileUploadRequest,
    DatasetMetadataUpdateRequest,
)
from core.service.api import dataset as dataset_api

router = APIRouter()


@router.get("/projects/{project_id}/datasets")
async def list_datasets(project_id: str):
    return yaml_response(dataset_api.list_datasets(project_id))


@router.post("/projects/{project_id}/datasets/files")
async def upload_dataset_file(project_id: str, request: Request):
    """PDF・DOCX・XLSXのファイルをDatasetとして追加する(中身はbase64)。"""
    body = await parse_yaml_body(request, DatasetFileUploadRequest)
    try:
        return yaml_response(dataset_api.upload_dataset_file(project_id, body))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/projects/{project_id}/datasets/{file_id}")
async def get_dataset_content(project_id: str, file_id: str):
    """CSVのDatasetの中身。CSV以外(PDF等)は400(ファイルそのものは.../fileで得る)。"""
    try:
        return yaml_response(dataset_api.get_dataset_content(project_id, file_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/projects/{project_id}/datasets/{file_id}/file")
async def get_dataset_file(project_id: str, file_id: str):
    """データ本体のファイルそのもの(YAMLではない)。PDF等ブラウザで表示できる形式はinline、
    DOCX・XLSXはダウンロード(attachment)で返す。"""
    location = dataset_api.get_dataset_file(project_id, file_id)
    return FileResponse(
        location.path,
        media_type=location.media_type,
        filename=location.filename,
        content_disposition_type="inline" if location.inline else "attachment",
    )


@router.get("/projects/{project_id}/datasets/{file_id}/metadata")
async def get_dataset_metadata_endpoint(project_id: str, file_id: str):
    """指定Datasetの「データメタデータYAML」を返す。まだ無い場合は404。"""
    return yaml_response(dataset_api.get_dataset_metadata(project_id, file_id))


@router.put("/projects/{project_id}/datasets/{file_id}/metadata")
async def update_dataset_metadata_endpoint(project_id: str, file_id: str, request: Request):
    """指定Datasetの「データメタデータYAML」の自由記述欄を更新する(無ければ新規作成)。"""
    body = await parse_yaml_body(request, DatasetMetadataUpdateRequest)
    return yaml_response(dataset_api.update_dataset_metadata_fields(project_id, file_id, body))


@router.delete("/projects/{project_id}/datasets/{file_id}")
async def delete_dataset_endpoint(project_id: str, file_id: str):
    """
    Dataset本体(CSV)・サイドカーのデータメタデータYAML・登録をまとめて削除する。
    取り消し不可のため、GUI側は削除前に確認する。
    """
    return yaml_response(dataset_api.delete_project_dataset(project_id, file_id))
