# core/service/process/edit/dataset_editor.py
"""
Dataset(CSV・PDF)の保存・改名・削除と、「データメタデータYAML」の作成・更新の手順。

save_dataset()(CSV)とsave_file_dataset()(PDF等のバイナリ)が、データ本体の保存・
dataset_registry(project.db)への登録・サイドカーYAMLの初期化(または追記)をまとめて行う、
Dataset保存の入口(登録とメタデータの手順は_register_with_metadataで共通)。core側の
処理が自分の出力をDatasetとして保存することもあるため、インターフェース(api層)ではなく
core側に置く。ファイル自体の読み書きはcore.infra.store.dataset_file_store。
"""

import csv
import io
import os
from datetime import UTC, datetime
from typing import Optional

from core.infra.store.dataset_file_store import (
    read_metadata,
    remove_dataset_files,
    rename_dataset_files,
    save_bytes,
    save_csv,
    write_metadata,
)
from core.infra.store.dataset_registry_store import (
    register_dataset,
    rename_registered_dataset,
    unregister_dataset,
)
from core.infra.store.project_file_store import read_project
from core.infra.store.project_registry_store import resolve_layout
from core.schema.formats.dataset_metadata import (
    DatasetCategory,
    DatasetColumnInfo,
    DatasetHistoryEntry,
    DatasetInfo,
    DatasetMetadata,
    DatasetProvenance,
)


def now() -> str:
    return datetime.now(UTC).astimezone().isoformat()


def _infer_columns_from_csv(csv_text: str) -> list[DatasetColumnInfo]:
    """CSVのヘッダー行から列名だけを拾い、type/descriptionは空のcolumnsを作る
    (メタデータYAML新規作成時の初期値。列名が空文字の列は無視する)。"""
    reader = csv.reader(io.StringIO(csv_text))
    try:
        header = next(reader)
    except StopIteration:
        return []
    return [DatasetColumnInfo(name=name) for name in header if name]


def sanitize_filename(label: str, default: str = "dataset.csv") -> str:
    """パストラバーサル対策を兼ねた、ファイル名のサニタイズ。"""
    safe_name = os.path.basename(label).replace(os.sep, "_")
    if not safe_name or safe_name in (".", ".."):
        safe_name = default
    return safe_name


def save_dataset(
    db_path: str,
    datasets_dir: str,
    filename: str,
    csv_text: str,
    *,
    drama_id: Optional[str],
    drama_title: Optional[str] = None,
    project_id: Optional[str] = None,
    project_name: Optional[str] = None,
    provenance: Optional[DatasetProvenance] = None,
    dataset_category: DatasetCategory = DatasetCategory.UNSPECIFIED,
) -> tuple[str, str]:
    """
    CSVの保存・dataset_registry(project.db)への登録・サイドカーYAMLの初期化
    (または追記)をまとめて行う。実際に保存したファイル名と、そのfile_id
    (不変のDataset識別子。dataset_registry_store.register_datasetが発行・管理する)を返す。

    同名のDatasetが既に存在する場合、サイドカーYAMLは作り直さず、既存の
    history(編集履歴)へ1件追記するだけにする(説明・タグ等、既に書かれた
    メタデータを保存の都度失わないため)。同名再保存では
    file_idもregistryに登録済みの値を引き継ぐ(register_dataset参照)。

    provenance(機構: manually_registered/system_derived)とdataset_category
    (種類: unspecified/reference)は別軸の分類で、いずれも
    呼び出し側が何を保存しようとしているか知っている前提で明示的に渡す
    (このモジュールでは推測しない)。
    """
    saved_filename = sanitize_filename(filename)
    save_csv(datasets_dir, saved_filename, csv_text)
    file_id = _register_with_metadata(
        db_path,
        datasets_dir,
        saved_filename,
        drama_id=drama_id,
        drama_title=drama_title,
        project_id=project_id,
        project_name=project_name,
        provenance=provenance,
        dataset_category=dataset_category,
        columns=_infer_columns_from_csv(csv_text),
    )
    return saved_filename, file_id


def save_file_dataset(
    db_path: str,
    datasets_dir: str,
    filename: str,
    data: bytes,
    *,
    drama_id: Optional[str],
    drama_title: Optional[str] = None,
    project_id: Optional[str] = None,
    project_name: Optional[str] = None,
    provenance: Optional[DatasetProvenance] = None,
    dataset_category: DatasetCategory = DatasetCategory.UNSPECIFIED,
) -> tuple[str, str]:
    """PDF等のバイナリのデータ本体を保存する(登録・サイドカーYAMLの扱いはsave_datasetと同じ。
    列は無い)。戻り値は(保存したファイル名, file_id)。"""
    saved_filename = sanitize_filename(filename)
    save_bytes(datasets_dir, saved_filename, data)
    file_id = _register_with_metadata(
        db_path,
        datasets_dir,
        saved_filename,
        drama_id=drama_id,
        drama_title=drama_title,
        project_id=project_id,
        project_name=project_name,
        provenance=provenance,
        dataset_category=dataset_category,
        columns=[],
    )
    return saved_filename, file_id


def _register_with_metadata(
    db_path: str,
    datasets_dir: str,
    saved_filename: str,
    *,
    drama_id: Optional[str],
    drama_title: Optional[str],
    project_id: Optional[str],
    project_name: Optional[str],
    provenance: Optional[DatasetProvenance],
    dataset_category: DatasetCategory,
    columns: list[DatasetColumnInfo],
) -> str:
    """保存済みのデータ本体をdataset_registryに登録し、サイドカーYAMLを初期化(または履歴を追記)する。"""
    file_id = register_dataset(db_path, saved_filename, drama_id)

    existing = read_metadata(datasets_dir, saved_filename)
    if existing is None:
        existing = DatasetMetadata(
            dataset={
                "file_id": file_id,
                "project_id": project_id,
                "project_name": project_name,
                "drama_id": drama_id,
                "drama_title": drama_title,
                "dataset_category": dataset_category,
                "created_at": now(),
            },
            provenance=provenance if provenance is not None else DatasetProvenance(),
            columns=columns,
        )
    elif not existing.dataset.file_id:
        existing.dataset.file_id = file_id
    append_history(existing, message="")
    write_metadata(datasets_dir, saved_filename, existing)
    return file_id


def rename_dataset(db_path: str, datasets_dir: str, old_filename: str, new_filename: str) -> str:
    """CSV・サイドカーYAML・dataset_registryの登録名をまとめてリネームする。"""
    sanitized_new_filename = sanitize_filename(new_filename)
    rename_dataset_files(datasets_dir, old_filename, sanitized_new_filename)
    rename_registered_dataset(db_path, old_filename, sanitized_new_filename)
    return sanitized_new_filename


def delete_dataset(db_path: str, datasets_dir: str, filename: str) -> None:
    """CSV本体・サイドカーのデータメタデータYAML・dataset_registryの登録を
    まとめて削除する(取り消し不可。呼び出し側で確認ダイアログを挟むこと)。"""
    remove_dataset_files(datasets_dir, filename)
    unregister_dataset(db_path, filename)


def save_project_dataset(
    project_id: str,
    csv_text: str,
    label: str,
    drama_id: Optional[str],
    drama_title: Optional[str] = None,
    provenance: Optional[DatasetProvenance] = None,
    dataset_category: DatasetCategory = DatasetCategory.UNSPECIFIED,
) -> tuple[str, str]:
    """
    save_dataset()の薄いラッパー。project_idから
    save_dataset()に必要なproject.dbのパス/datasets_dir/project名を揃える。
    戻り値は(保存したファイル名, file_id)。
    """
    layout = resolve_layout(project_id)
    project_db = layout.project_db_path
    datasets_dir = layout.datasets_dir
    project_name = read_project(layout.root_dir).name
    return save_dataset(
        project_db,
        datasets_dir,
        label,
        csv_text,
        drama_id=drama_id,
        drama_title=drama_title,
        project_id=project_id,
        project_name=project_name,
        provenance=provenance,
        dataset_category=dataset_category,
    )


def save_project_file_dataset(
    project_id: str,
    data: bytes,
    label: str,
    drama_id: Optional[str],
    drama_title: Optional[str] = None,
    provenance: Optional[DatasetProvenance] = None,
    dataset_category: DatasetCategory = DatasetCategory.UNSPECIFIED,
) -> tuple[str, str]:
    """save_file_dataset()の薄いラッパー(save_project_datasetのバイナリ版)。戻り値は(保存したファイル名, file_id)。"""
    layout = resolve_layout(project_id)
    return save_file_dataset(
        layout.project_db_path,
        layout.datasets_dir,
        label,
        data,
        drama_id=drama_id,
        drama_title=drama_title,
        project_id=project_id,
        project_name=read_project(layout.root_dir).name,
        provenance=provenance,
        dataset_category=dataset_category,
    )


def update_editable_fields(
    datasets_dir: str,
    csv_filename: str,
    *,
    file_id: str,
    project_id: str,
    project_name: str,
    drama_id: Optional[str],
    drama_title: Optional[str],
    description: Optional[str],
    source: Optional[str],
    collected_at: Optional[str],
    tags: list[str],
    notes: Optional[str],
    columns: list[DatasetColumnInfo],
    history_message: str = "",
) -> DatasetMetadata:
    """
    データメタデータYAMLの自由記述欄(description/source/collected_at/tags/
    notes/columns)を更新する。GUIからの編集(project_overview_panel.js)用。

    サイドカーYAMLがまだ無い場合(手動で配置したファイル等)は、save_dataset()の新規作成時と
    同じ形で作成する(upsert)。project_id/project_name/drama_id/drama_title/created_atは
    その時点のスナップショットとして新規作成時のみ設定し、既存メタデータを
    更新する場合はここでは変更しない(ドラマの題が後から変わっても、
    メタデータ上の記録は作成時点のまま保つ設計)。
    file_id(呼び出し側がdataset_registry_store.get_or_create_file_idで解決済みの値)は
    新規作成時に設定し、既存メタデータに欠けていれば補完する(不変の識別子
    なので、既に値がある場合は上書きしない)。
    """
    metadata = read_metadata(datasets_dir, csv_filename)
    if metadata is None:
        metadata = DatasetMetadata(
            dataset=DatasetInfo(
                file_id=file_id,
                project_id=project_id,
                project_name=project_name,
                drama_id=drama_id,
                drama_title=drama_title,
                created_at=now(),
            )
        )
    elif not metadata.dataset.file_id:
        metadata.dataset.file_id = file_id
    metadata.dataset.description = description
    metadata.dataset.source = source
    metadata.dataset.collected_at = collected_at
    metadata.dataset.tags = tags
    metadata.dataset.notes = notes
    metadata.columns = columns
    append_history(metadata, history_message)
    write_metadata(datasets_dir, csv_filename, metadata)
    return metadata


def append_history(metadata: DatasetMetadata, message: str = "") -> DatasetMetadata:
    """
    historyへ1件追記する(古い順に末尾へ追加していく運用。最終更新日時は
    history[-1].updated_atで分かるため、別途保持しない。詳細はcore.schema.
    formats.dataset_metadataのモジュールdocstring参照)。messageは空文字列でもよい。
    """
    metadata.dataset.history.append(DatasetHistoryEntry(updated_at=now(), message=message))
    return metadata
