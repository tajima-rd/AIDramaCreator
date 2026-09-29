# core/service/api/dataset.py
"""
Datasetの公開API。

Datasetはfile_idを主キーとして受け取り、実際のファイル操作の直前だけfilenameへ解決する
(CSV本体はdatasets_dir配下にfilenameで実在するため)。

エラーは例外で返す: file_idに対応するDatasetが無ければDatasetNotFoundError、サイドカーの
データメタデータYAMLが無ければDatasetMetadataNotFoundError。

ドラマ(QIDMのDomainに相当する概念として検討中)への割り当て・ドラマごとの一覧と保存は、ドラマの定義が
できるまで持たない(docs/future_design.md)。
"""

import base64
import binascii
import io
import os
import zipfile

from core.infra.store.dataset_file_store import read_metadata as read_dataset_metadata
from core.infra.store.dataset_registry_store import (
    get_or_create_file_id,
    list_dataset_entries,
    resolve_filename,
)
from core.infra.store.project_file_store import read_project
from core.infra.store.project_registry_store import resolve_layout
from core.project.dataset import (
    INLINE_FORMATS,
    MEDIA_TYPES,
    DatasetMetadataNotFoundError,
    DatasetNotFoundError,
    file_format,
)
from core.schema import (
    DatasetCategory,
    DatasetContent,
    DatasetDeleteResult,
    DatasetFileLocation,
    DatasetFileUploadRequest,
    DatasetListResult,
    DatasetMetadata,
    DatasetMetadataUpdateRequest,
    DatasetProvenance,
    DatasetSummary,
)
from core.service.process.edit.dataset_editor import (
    delete_dataset,
    save_project_file_dataset,
)
from core.service.process.edit.dataset_editor import (
    update_editable_fields as update_dataset_metadata,
)


def _dataset_drama_map(project_id: str) -> dict[str, str | None]:
    """dataset_registry(project.db)から、filename -> drama_idの対応を作る。"""
    project_db = resolve_layout(project_id).project_db_path
    return {
        entry["filename"]: entry.get("drama_id")
        for entry in list_dataset_entries(project_db)
        if entry.get("filename")
    }


def _list_dataset_summaries(project_id: str) -> list[DatasetSummary]:
    """
    datasets/配下のファイル一覧に、dataset_registry(project.db)に記録された
    drama_idを付与して返す(未記録のファイルはdrama_id=Noneの未割当扱い)。

    registryに未登録のファイル(手動で配置したもの等)は、
    ここで初めてアクセスされた時点でfile_idを自動採番して登録する
    (get_or_create_file_id。「システム内部ではfilenameに依存せずfile_idで
    追跡する」という設計上、一覧に出す以上は必ずfile_idを持たせる)。

    core.service.process.edit.dataset_editor.save_dataset()が併置する「データメタデータYAML」
    (「{データ本体のファイル名}.yaml」)は、データ本体とは別の独立した
    Datasetとして数えない(一覧からは除外する)。データメタデータYAMLが
    存在すれば、その`dataset.dataset_category`(無ければNone)も付与する。
    """
    project_db = resolve_layout(project_id).project_db_path
    datasets_dir = resolve_layout(project_id).datasets_dir
    drama_map = _dataset_drama_map(project_id)
    datasets = []
    if os.path.isdir(datasets_dir):
        all_filenames = set(os.listdir(datasets_dir))
        for filename in sorted(all_filenames):
            full_path = os.path.join(datasets_dir, filename)
            if not os.path.isfile(full_path):
                continue
            if filename.endswith(".yaml") and filename[: -len(".yaml")] in all_filenames:
                continue
            metadata = read_dataset_metadata(datasets_dir, filename)
            dataset_category = metadata.dataset.dataset_category if metadata else None
            datasets.append(
                DatasetSummary(
                    file_id=get_or_create_file_id(project_db, filename),
                    filename=filename,
                    size_bytes=os.path.getsize(full_path),
                    drama_id=drama_map.get(filename),
                    dataset_category=dataset_category,
                    file_format=file_format(filename),
                )
            )
    return datasets


def _dataset_path(project_id: str, filename: str) -> str:
    """filenameをdatasets_dir配下のパスに解決する(パストラバーサル対策込み)。"""
    datasets_dir = resolve_layout(project_id).datasets_dir
    safe_name = os.path.basename(filename)
    full_path = os.path.join(datasets_dir, safe_name)
    if not safe_name or not os.path.isfile(full_path):
        raise DatasetNotFoundError(filename)
    return full_path


def _resolve_existing_dataset(project_id: str, file_id: str) -> str:
    """file_idをfilenameへ解決し、CSV本体が実在することまで確かめてfilenameを返す。"""
    filename = resolve_filename(resolve_layout(project_id).project_db_path, file_id)
    if filename is None:
        raise DatasetNotFoundError(file_id)
    _dataset_path(project_id, filename)  # 存在確認・パストラバーサル対策
    return filename


def list_datasets(project_id: str) -> DatasetListResult:
    resolve_layout(project_id)  # プロジェクトの存在確認(未登録ならProjectNotFoundError)
    return DatasetListResult(datasets=_list_dataset_summaries(project_id))


def get_dataset_content(project_id: str, file_id: str) -> DatasetContent:
    """CSVのDatasetの中身(文字列)。CSV以外(PDF等)はValueError(ファイルそのものはget_dataset_file)。"""
    filename = _resolve_existing_dataset(project_id, file_id)
    if file_format(filename) != "csv":
        raise ValueError(f"CSVのDatasetではありません: {filename}")
    with open(_dataset_path(project_id, filename), encoding="utf-8") as f:
        csv_text = f.read()
    drama_id = _dataset_drama_map(project_id).get(filename)
    return DatasetContent(file_id=file_id, filename=filename, drama_id=drama_id, csv=csv_text)


def get_dataset_file(project_id: str, file_id: str) -> DatasetFileLocation:
    """データ本体のファイルの所在と種類(PDFの表示・ダウンロード用)。"""
    filename = _resolve_existing_dataset(project_id, file_id)
    return DatasetFileLocation(
        path=_dataset_path(project_id, filename),
        filename=filename,
        media_type=MEDIA_TYPES.get(file_format(filename), "application/octet-stream"),
        inline=file_format(filename) in INLINE_FORMATS,
    )


def _is_office_file(data: bytes, required_member: str) -> bool:
    """DOCX・XLSXはZIPで、中にWord・Excelの本体(required_member)がある。"""
    if not data.startswith(b"PK\x03\x04"):
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return required_member in archive.namelist()
    except zipfile.BadZipFile:
        return False


# ファイルとして追加できる形式と、その中身の確かめ方(拡張子だけでなく中身も確かめる)
UPLOADABLE_FILE_CHECKS = {
    "pdf": lambda data: data.startswith(b"%PDF-"),
    "docx": lambda data: _is_office_file(data, "word/document.xml"),
    "xlsx": lambda data: _is_office_file(data, "xl/workbook.xml"),
}
MAX_UPLOAD_BYTES = 30 * 1024 * 1024


def upload_dataset_file(project_id: str, request: DatasetFileUploadRequest) -> DatasetSummary:
    """PDF・DOCX・XLSXのファイルをDatasetとして追加する(同名ファイルは上書き)。ドラマには未割当。

    参考資料として追加するため、dataset_categoryの既定はreference。
    """
    fmt = file_format(request.filename)
    if fmt not in UPLOADABLE_FILE_CHECKS:
        raise ValueError(f"ファイルとして追加できるのは{', '.join(UPLOADABLE_FILE_CHECKS)}だけです: {request.filename}")
    try:
        data = base64.b64decode(request.content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("ファイルの中身(base64)を読めません。") from exc
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError(f"ファイルが大きすぎます(上限{MAX_UPLOAD_BYTES // (1024 * 1024)}MB)。")
    if not UPLOADABLE_FILE_CHECKS[fmt](data):
        raise ValueError(f"{fmt.upper()}ファイルではありません: {request.filename}")

    saved_filename, saved_file_id = save_project_file_dataset(
        project_id,
        data,
        request.filename,
        drama_id=None,
        provenance=DatasetProvenance(),
        dataset_category=request.dataset_category or DatasetCategory.REFERENCE,
    )
    return next(d for d in _list_dataset_summaries(project_id) if d.file_id == saved_file_id)


def get_dataset_metadata(project_id: str, file_id: str) -> DatasetMetadata:
    """指定Datasetの「データメタデータYAML」(description/provenance/columns等)を返す。"""
    filename = _resolve_existing_dataset(project_id, file_id)
    metadata = read_dataset_metadata(resolve_layout(project_id).datasets_dir, filename)
    if metadata is None:
        raise DatasetMetadataNotFoundError(file_id)
    return metadata


def update_dataset_metadata_fields(
    project_id: str, file_id: str, request: DatasetMetadataUpdateRequest
) -> DatasetMetadata:
    """
    指定Datasetの「データメタデータYAML」の自由記述欄(description/source/
    collected_at/tags/notes/columns)を更新する。サイドカーYAMLがまだ無い
    場合は新規作成する(upsert。メタデータが無いDatasetも編集できるようにするため)。
    """
    filename = _resolve_existing_dataset(project_id, file_id)
    root_dir = resolve_layout(project_id).root_dir
    datasets_dir = resolve_layout(project_id).datasets_dir
    drama_id = _dataset_drama_map(project_id).get(filename)
    project_name = read_project(root_dir).name
    return update_dataset_metadata(
        datasets_dir,
        filename,
        file_id=file_id,
        project_id=project_id,
        project_name=project_name,
        drama_id=drama_id,
        drama_title=None,  # ドラマの定義ができたら、その題を引く
        description=request.description,
        source=request.source,
        collected_at=request.collected_at,
        tags=request.tags,
        notes=request.notes,
        columns=request.columns,
        history_message=request.message,
    )


def delete_project_dataset(project_id: str, file_id: str) -> DatasetDeleteResult:
    """Dataset本体(CSV)・サイドカーのデータメタデータYAML・登録をまとめて削除する。"""
    filename = _resolve_existing_dataset(project_id, file_id)
    delete_dataset(resolve_layout(project_id).project_db_path, resolve_layout(project_id).datasets_dir, filename)
    return DatasetDeleteResult(file_id=file_id, filename=filename)
