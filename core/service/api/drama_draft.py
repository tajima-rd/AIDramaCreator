# core/service/api/drama_draft.py
"""
作品モデルの下書きの公開API(docs/architecture.md 7節・docs/database_design.md)。

- 下書きは確定した最新の版を元に作る。Apply・直接編集・取り込みは、部分YAML(モデル定義YAMLの形で変えたい部分だけ。
  文字列のまま受け取る)を下書きの中身に重ねる。取り込みはreplaceで中身全体を置き換えられる。
- 確定すると正本が書き換わり、版が1つできる。

エラーは例外で返す: project_idが未登録ならProjectNotFoundError、下書きが無ければDraftNotFoundError、
元にした版のあとに別の下書きが確定されていればDraftConflictError(ValueErrorの一種)、YAMLの形・参照の誤りや
openでない下書きの変更はValueError、YAMLとして読めなければyaml.YAMLError、取り込むファイルが無ければFileNotFoundError。
地図(KML・GeoPackage)の取り込みと地図の画面の保存で、読めない・端点が場所に入らない等もValueError。
"""

import base64
import binascii
import os
import tempfile
from typing import Optional

from core.gis.io.geopackage import write_feature_layers
from core.infra.store.drama_version_store import DraftInfo, DraftNotFoundError
from core.infra.store.project_registry_store import resolve_layout
from core.schema import (
    DramaDraftChangeResult,
    DramaDraftConfirmRequest,
    DramaDraftConfirmResult,
    DramaDraftCreateRequest,
    DramaDraftGeodataImportRequest,
    DramaDraftGeodataImportResult,
    DramaDraftImportPathRequest,
    DramaDraftInfo,
    DramaDraftListResult,
    DramaDraftMapAuxiliaryFeature,
    DramaDraftMapAuxiliaryLayer,
    DramaDraftMapLocation,
    DramaDraftMapResult,
    DramaDraftMapSaveRequest,
    DramaDraftMapSaveResult,
    DramaDraftMapSiteFlow,
    DramaDraftRevisionListResult,
    DramaDraftRevisionSummary,
)
from core.schema.formats.dramaturgy_definition import DramaturgyDefinition
from core.service.api.drama_model import definition_from_yaml
from core.service.process.edit import drama_draft_editor, geodata_importer, location_map_editor
from core.service.process.edit.dataset_editor import save_project_file_dataset
from core.service.process.edit.drama_draft_editor import DraftConflictError

__all__ = [
    "DraftConflictError",
    "DraftNotFoundError",
    "apply_proposal",
    "confirm_draft",
    "create_draft",
    "discard_draft",
    "edit_draft",
    "get_draft",
    "get_draft_content",
    "get_map",
    "import_geodata",
    "import_path",
    "import_yaml",
    "list_drafts",
    "list_revisions",
    "save_map",
    "undo",
]


def _db_path(project_id: str) -> str:
    return resolve_layout(project_id).project_db_path


def _to_info(draft: DraftInfo) -> DramaDraftInfo:
    return DramaDraftInfo(
        draft_id=draft.id,
        title=draft.title,
        base_version=draft.base_version,
        status=draft.status,
        created_at=draft.created_at,
        updated_at=draft.updated_at,
    )


def create_draft(project_id: str, request: DramaDraftCreateRequest) -> DramaDraftInfo:
    return _to_info(drama_draft_editor.create_draft(_db_path(project_id), request.title))


def list_drafts(project_id: str, status: Optional[str] = None) -> DramaDraftListResult:
    drafts = drama_draft_editor.list_drafts(_db_path(project_id), status)
    return DramaDraftListResult(drafts=[_to_info(draft) for draft in drafts])


def get_draft(project_id: str, draft_id: str) -> DramaDraftInfo:
    return _to_info(drama_draft_editor.read_draft(_db_path(project_id), draft_id))


def get_draft_content(
    project_id: str, draft_id: str, revision: Optional[int] = None
) -> DramaturgyDefinition:
    """下書きの中身(revisionを渡せば、履歴のその行)。"""
    return definition_from_yaml(
        drama_draft_editor.draft_yaml(_db_path(project_id), draft_id, revision)
    )


def list_revisions(project_id: str, draft_id: str) -> DramaDraftRevisionListResult:
    revisions = drama_draft_editor.list_revisions(_db_path(project_id), draft_id)
    return DramaDraftRevisionListResult(
        revisions=[
            DramaDraftRevisionSummary(
                revision=r.revision, operation=r.operation, created_at=r.created_at
            )
            for r in revisions
        ]
    )


def apply_proposal(project_id: str, draft_id: str, yaml_text: str) -> DramaDraftChangeResult:
    """生成AIの提案(部分YAML)を反映する(Apply)。"""
    revision = drama_draft_editor.apply_to_draft(_db_path(project_id), draft_id, yaml_text)
    return DramaDraftChangeResult(revision=revision)


def edit_draft(project_id: str, draft_id: str, yaml_text: str) -> DramaDraftChangeResult:
    """利用者の直接編集(部分YAML)を保存する。"""
    revision = drama_draft_editor.edit_draft(_db_path(project_id), draft_id, yaml_text)
    return DramaDraftChangeResult(revision=revision)


def import_yaml(
    project_id: str, draft_id: str, yaml_text: str, replace: bool = False
) -> DramaDraftChangeResult:
    """モデル定義YAMLの文字列(`---`で区切った複数の文書でもよい)を取り込む。"""
    revision = drama_draft_editor.import_yaml(
        _db_path(project_id), draft_id, yaml_text, replace=replace
    )
    return DramaDraftChangeResult(revision=revision)


def import_path(
    project_id: str, draft_id: str, request: DramaDraftImportPathRequest
) -> DramaDraftChangeResult:
    """サーバーの手元のモデル定義YAML(ファイルか、分割したファイルを置いたディレクトリ)を取り込む。"""
    revision = drama_draft_editor.import_definition(
        _db_path(project_id), draft_id, request.path, replace=request.replace
    )
    return DramaDraftChangeResult(revision=revision)


MAX_GEODATA_BYTES = 30 * 1024 * 1024
AUXILIARY_SUFFIX = "_補助情報.gpkg"  # 補助情報のDatasetのファイル名(取り込んだファイル名の拡張子をこれに替える)


def import_geodata(
    project_id: str, draft_id: str, request: DramaDraftGeodataImportRequest
) -> DramaDraftGeodataImportResult:
    """
    場所の地図(KML・KMZ・GeoPackage)を、下書きの作品に取り込む(core.service.process.edit.geodata_importer)。
    補助情報の層があれば、GeoPackageにまとめて、作品に割り当てたDatasetとして保存する(同じ名前なら上書き。
    Datasetは下書きを通らず、すぐに保存される)。
    """
    try:
        data = base64.b64decode(request.content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("ファイルの中身(base64)を読めません。") from exc
    if len(data) > MAX_GEODATA_BYTES:
        raise ValueError(f"ファイルが大きすぎます(上限{MAX_GEODATA_BYTES // (1024 * 1024)}MB)。")
    result = geodata_importer.import_geodata(
        _db_path(project_id), draft_id, request.dramaturgy_id, request.filename, data
    )
    file_id = filename = None
    if result.auxiliary:
        label = os.path.splitext(os.path.basename(request.filename))[0] + AUXILIARY_SUFFIX
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "auxiliary.gpkg")
            write_feature_layers(path, result.auxiliary)
            with open(path, "rb") as f:
                filename, file_id = save_project_file_dataset(
                    project_id,
                    f.read(),
                    label,
                    drama_id=request.dramaturgy_id,
                    drama_title=result.dramaturgy_title,
                )
    return DramaDraftGeodataImportResult(
        revision=result.revision,
        locations_created=result.locations_created,
        locations_updated=result.locations_updated,
        site_flows_created=result.site_flows_created,
        site_flows_updated=result.site_flows_updated,
        auxiliary_layers={name: len(features) for name, features in result.auxiliary.items()},
        auxiliary_file_id=file_id,
        auxiliary_filename=filename,
    )


def get_map(project_id: str, draft_id: str, dramaturgy_id: str) -> DramaDraftMapResult:
    """下書きの作品の地図(core.service.process.edit.location_map_editor)。補助情報は作品に割り当てたGeoPackageのDataset。"""
    layout = resolve_layout(project_id)
    result = location_map_editor.read_map(
        layout.project_db_path, layout.datasets_dir, draft_id, dramaturgy_id
    )
    return DramaDraftMapResult(
        dramaturgy_id=dramaturgy_id,
        dramaturgy_title=result.dramaturgy_title,
        locations=[DramaDraftMapLocation(**row) for row in result.locations],
        site_flows=[DramaDraftMapSiteFlow(**row) for row in result.site_flows],
        auxiliary_layers=[
            DramaDraftMapAuxiliaryLayer(
                dataset_filename=layer.dataset_filename,
                layer=layer.layer,
                features=[
                    DramaDraftMapAuxiliaryFeature(geometry=geometry, properties=properties)
                    for geometry, properties in layer.features
                ],
            )
            for layer in result.auxiliary
        ],
        warnings=result.warnings,
    )


def save_map(
    project_id: str, draft_id: str, request: DramaDraftMapSaveRequest
) -> DramaDraftMapSaveResult:
    """地図の画面の状態を、下書きの作品に保存する(直接編集。地図の取り込みと同じ規則)。"""
    result = location_map_editor.save_map(
        _db_path(project_id),
        draft_id,
        request.dramaturgy_id,
        [item.model_dump(exclude={"used_in_scenes"}) for item in request.locations],
        [item.model_dump(exclude={"origin_id", "destination_id"}) for item in request.site_flows],
    )
    return DramaDraftMapSaveResult(
        revision=result.revision,
        locations_created=result.locations_created,
        locations_updated=result.locations_updated,
        site_flows_created=result.site_flows_created,
        site_flows_updated=result.site_flows_updated,
    )


def undo(project_id: str, draft_id: str) -> DramaDraftChangeResult:
    return DramaDraftChangeResult(revision=drama_draft_editor.undo(_db_path(project_id), draft_id))


def confirm_draft(
    project_id: str, draft_id: str, request: DramaDraftConfirmRequest
) -> DramaDraftConfirmResult:
    version = drama_draft_editor.confirm_draft(_db_path(project_id), draft_id, request.note)
    return DramaDraftConfirmResult(version=version)


def discard_draft(project_id: str, draft_id: str) -> DramaDraftInfo:
    db_path = _db_path(project_id)
    drama_draft_editor.discard_draft(db_path, draft_id)
    return _to_info(drama_draft_editor.read_draft(db_path, draft_id))
