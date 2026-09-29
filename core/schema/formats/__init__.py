# core/schema/formats/__init__.py
"""
ディスクに永続化されるファイル形式のスキーマ。

特定のHTTPエンドポイントに紐づかず、ファイル形式そのものを宣言する点でAPIリクエスト/レスポンス
の型(core.schema.api)とは異なる。

- dataset_metadata: Datasetに併置する「データメタデータYAML」
- reference_language: 参考資料の言語と、資料の検索で使う決まった問いの訳
"""

from .dataset_metadata import (
    DatasetCategory,
    DatasetColumnInfo,
    DatasetHistoryEntry,
    DatasetInfo,
    DatasetMetadata,
    DatasetProvenance,
    DatasetProvenanceProcess,
    DatasetSourceRef,
)
from .reference_language import ReferenceLanguage

__all__ = [
    "DatasetMetadata",
    "DatasetInfo",
    "DatasetProvenance",
    "DatasetProvenanceProcess",
    "DatasetCategory",
    "DatasetSourceRef",
    "DatasetHistoryEntry",
    "DatasetColumnInfo",
    "ReferenceLanguage",
]
