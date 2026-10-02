# core/project/dataset.py
"""
プロジェクト内のDataset(datasets/配下のデータ本体(CSV・PDF)と、サイドカーの「データメタデータYAML」)の定義。

データ本体の形式(file_format)はファイル名の拡張子から決まる(FILE_FORMATS)。CSVは表のデータで
分析に使い、PDF・DOCX・XLSXは論文やその補足資料等の参考資料(2026-09-28追加、生成AIでモデルを
作る元になる)。

Datasetはfile_id(filenameに依存しない不変の識別子、project.dbのdataset_registry)で追跡し、
実体はdatasets/配下にfilenameで存在する。データメタデータYAMLは「{CSVファイル名}.yaml」
(拡張子を置き換えず追加する)で、CSVと同じディレクトリに置く。
"""

import os
from dataclasses import dataclass
from typing import Optional

from core.project.project import ProjectLayout

METADATA_SUFFIX = ".yaml"

# 拡張子 → データ本体の形式。ここに無い拡張子は"other"(一覧には出るが、表示・分析はできない)
FILE_FORMATS = {".csv": "csv", ".pdf": "pdf", ".docx": "docx", ".xlsx": "xlsx", ".gpkg": "gpkg"}
MEDIA_TYPES = {
    "csv": "text/csv",
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "gpkg": "application/geopackage+sqlite3",  # 場所の地図の補助情報(地図の取り込みが作る。2026-10-02)
}
# ブラウザの中で表示できる形式(それ以外はダウンロードさせる)
INLINE_FORMATS = ("csv", "pdf")


def file_format(filename: str) -> str:
    """ファイル名の拡張子から、データ本体の形式("csv"・"pdf"・"other")を決める。"""
    return FILE_FORMATS.get(os.path.splitext(filename)[1].lower(), "other")


class DatasetNotFoundError(LookupError):
    """指定したfile_id/filenameのDatasetが見つからない。"""


class DatasetMetadataNotFoundError(LookupError):
    """Dataset本体はあるが、サイドカーのデータメタデータYAMLがまだ無い。"""


def metadata_filename(filename: str) -> str:
    """CSVファイル名から、サイドカーのデータメタデータYAMLのファイル名を決める規則。"""
    return f"{filename}{METADATA_SUFFIX}"


@dataclass(frozen=True)
class Dataset:
    """プロジェクト内の1つのDataset。"""

    filename: str
    layout: ProjectLayout
    file_id: Optional[str] = None
    drama_id: Optional[str] = None

    @property
    def file_format(self) -> str:
        return file_format(self.filename)

    @property
    def path(self) -> str:
        return os.path.join(self.layout.datasets_dir, self.filename)

    @property
    def metadata_path(self) -> str:
        return os.path.join(self.layout.datasets_dir, metadata_filename(self.filename))
