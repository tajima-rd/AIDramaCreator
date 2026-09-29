# core/infra/store/dataset_file_store.py
"""
Dataset(datasets/配下のCSV本体)と、サイドカーの「データメタデータYAML」
(core.schema.formats.dataset_metadata.DatasetMetadata)のファイルの読み書き。
サイドカーのファイル名の規則はcore.project.dataset.metadata_filename。

保存・改名・削除・メタデータ更新の手順(dataset_registryへの登録等を含む)は
core.service.process.edit.dataset_editorが担い、ここはファイル操作のみ。

参考資料の検索の索引(core.genai.rag.ChunkIndex、npz)はdatasets/.index/<ファイル名>.npzに、資料の言語と
決まった問いの訳(core.schema.formats.reference_language.ReferenceLanguage)は
datasets/.index/<ファイル名>.language.yamlに置く(index_path・language_path)。作るのは使う側(core.service.process.genai.reference_searcher)で、改名・削除は
Datasetの本体と一緒に行う。Datasetの一覧はファイルだけを数えるため、.index/は現れない。
"""

import os

import yaml

from core.project.dataset import metadata_filename
from core.schema.formats.dataset_metadata import DatasetMetadata
from core.schema.formats.reference_language import ReferenceLanguage

INDEX_DIRNAME = ".index"


def save_csv(datasets_dir: str, filename: str, csv_text: str) -> None:
    """CSVをdatasets_dir配下へ保存する(ファイル名は既にサニタイズ済みの前提)。"""
    os.makedirs(datasets_dir, exist_ok=True)
    dest_path = os.path.join(datasets_dir, filename)
    with open(dest_path, "w", encoding="utf-8") as f:
        f.write(csv_text)


def save_bytes(datasets_dir: str, filename: str, data: bytes) -> None:
    """バイナリのデータ本体(PDF等)をdatasets_dir配下へ保存する(ファイル名は既にサニタイズ済みの前提)。"""
    os.makedirs(datasets_dir, exist_ok=True)
    with open(os.path.join(datasets_dir, filename), "wb") as f:
        f.write(data)


def rename_dataset_files(datasets_dir: str, old_filename: str, new_filename: str) -> None:
    """
    CSVと、存在すればそのサイドカーYAMLをまとめてリネームする。
    新しい名前のCSVが既に存在する場合はFileExistsErrorを送出する。
    """
    old_csv_path = os.path.join(datasets_dir, old_filename)
    new_csv_path = os.path.join(datasets_dir, new_filename)
    if not os.path.isfile(old_csv_path):
        raise FileNotFoundError(f"dataset not found: {old_filename}")
    if os.path.exists(new_csv_path):
        raise FileExistsError(f"すでに同名のdatasetが存在します: {new_filename}")

    os.rename(old_csv_path, new_csv_path)

    old_sidecar = sidecar_path(datasets_dir, old_filename)
    if os.path.isfile(old_sidecar):
        os.rename(old_sidecar, sidecar_path(datasets_dir, new_filename))

    for derived_path in (index_path, language_path):
        old_path = derived_path(datasets_dir, old_filename)
        if os.path.isfile(old_path):
            os.rename(old_path, derived_path(datasets_dir, new_filename))


def remove_dataset_files(datasets_dir: str, filename: str) -> None:
    """CSV本体と、存在すればそのサイドカーYAML・検索の索引・資料の言語を削除する(存在しないものは無視する)。"""
    csv_path = os.path.join(datasets_dir, filename)
    if os.path.isfile(csv_path):
        os.remove(csv_path)
    for path in (
        sidecar_path(datasets_dir, filename),
        index_path(datasets_dir, filename),
        language_path(datasets_dir, filename),
    ):
        if os.path.isfile(path):
            os.remove(path)


def sidecar_path(datasets_dir: str, csv_filename: str) -> str:
    return os.path.join(datasets_dir, metadata_filename(csv_filename))


def index_path(datasets_dir: str, filename: str) -> str:
    """参考資料の検索の索引(npz)のパス。"""
    return os.path.join(datasets_dir, INDEX_DIRNAME, f"{filename}.npz")


def language_path(datasets_dir: str, filename: str) -> str:
    """参考資料の言語と決まった問いの訳(YAML)のパス。"""
    return os.path.join(datasets_dir, INDEX_DIRNAME, f"{filename}.language.yaml")


def read_reference_language(datasets_dir: str, filename: str) -> ReferenceLanguage | None:
    path = language_path(datasets_dir, filename)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return ReferenceLanguage.model_validate(yaml.safe_load(f) or {})


def write_reference_language(datasets_dir: str, filename: str, language: ReferenceLanguage) -> None:
    path = language_path(datasets_dir, filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(language.model_dump(), f, allow_unicode=True, sort_keys=False)


def read_metadata(datasets_dir: str, csv_filename: str) -> DatasetMetadata | None:
    """サイドカーYAMLを読む。存在しなければNone(メタデータ無し、として扱う)。"""
    path = sidecar_path(datasets_dir, csv_filename)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        spec = yaml.safe_load(f) or {}
    return DatasetMetadata.model_validate(spec)


def write_metadata(datasets_dir: str, csv_filename: str, metadata: DatasetMetadata) -> None:
    path = sidecar_path(datasets_dir, csv_filename)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(
            # mode="json"でDatasetProvenanceProcess(Enum)をプレーンな文字列値へ
            # 変換する(既定のmode="python"のままだとEnumメンバーがそのまま
            # 残り、yaml.safe_dumpが非対応の型としてRepresenterErrorになる)。
            metadata.model_dump(mode="json"),
            f,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )
