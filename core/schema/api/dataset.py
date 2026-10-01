# core/schema/api/dataset.py
from typing import Optional

from pydantic import BaseModel

from core.schema.formats.dataset_metadata import (
    DatasetCategory,
    DatasetColumnInfo,
)


class DatasetSummary(BaseModel):
    file_id: str  # filenameに依存しない不変の識別子(core.infra.store.dataset_registry_store)
    filename: str
    size_bytes: int
    drama_id: Optional[str] = None
    dataset_category: Optional[DatasetCategory] = None  # データメタデータYAMLのdataset.dataset_category(あれば)
    file_format: str = "csv"  # データ本体の形式(拡張子から決まる。"csv"・"pdf"・"docx"・"xlsx"・"other")

class DatasetListResult(BaseModel):
    datasets: list[DatasetSummary]

class DatasetContent(BaseModel):
    file_id: str
    filename: str
    drama_id: Optional[str]
    csv: str

class DatasetFileUploadRequest(BaseModel):
    """PDF等のファイルをDatasetとして追加する。APIはYAMLでやり取りするため、ファイルの中身は
    base64で渡す。ドラマへの割り当て(drama_id)は、ドラマの定義ができるまで受け取らない(常に未割当)。"""

    filename: str
    content_base64: str
    dataset_category: Optional[DatasetCategory] = None


class DatasetFileLocation(BaseModel):
    """データ本体のファイルの所在(GET .../datasets/{file_id}/fileがファイルそのものを返すために使う)。"""

    path: str
    filename: str
    media_type: str
    inline: bool  # ブラウザの中で表示できる形式か(できなければダウンロードさせる)


class DatasetDeleteResult(BaseModel):
    file_id: str
    filename: str

class DatasetMetadataUpdateRequest(BaseModel):
    description: Optional[str] = None
    source: Optional[str] = None
    collected_at: Optional[str] = None
    tags: list[str] = []
    notes: Optional[str] = None
    columns: list[DatasetColumnInfo] = []
    message: str = ""
