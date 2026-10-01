# core/schema/formats/dataset_metadata.py
"""
Dataset(datasets/配下のデータ本体)に併置する「データメタデータYAML」
(「{データ本体のファイル名}.yaml」、拡張子を置き換えず追加する命名)の形。
Datasetの帳簿(project.dbのdataset_registryテーブル。file_id/filename/
drama_id/imported_at、プロジェクト内部の管理情報)とは役割を分けており、こちらは
自由記述のメタデータ・生成元情報・列の補足だけを持つ。

file_id(不変のDataset識別子)はfilenameへの依存を無くすために導入した
もので、registry(project.dbのdataset_registry)が発行・管理する。
サイドカーYAML側のDatasetInfo.file_idは、登録時点の値をそのまま複製した
もの(registryが単一の真実の情報源)。

historyは編集履歴を古い順に末尾へ追記していく方式(gitのコミット履歴の
イメージ。ただしmessageは空文字列でもよい)。最終更新日時は
history[-1].updated_atから分かるため、別途「最終更新日時」フィールドは
持たない。
"""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel


class DatasetSourceRef(BaseModel):
    kind: str
    id: str


class DatasetProvenanceProcess(str, Enum):
    """provenance.processの値。このDatasetがどういう機構でシステムに
    入ったか(だけ)を表す2値。「どんな種類のデータか」はDatasetInfo.
    dataset_category(DatasetCategory)側が持つ、完全に別軸の分類であり、
    この列挙とは混同しないこと。"""

    MANUALLY_REGISTERED = "manually_registered"  # 人間がGUI経由で明示的に追加/登録した
    SYSTEM_DERIVED = "system_derived"  # 内部処理が自動生成した


class DatasetCategory(str, Enum):
    """DatasetInfo.dataset_categoryの値。このDatasetがどんな種類のデータかを
    表す分類で、処理が「自分が受け付けるのはこの種類のDatasetだけ」と絞り込むために使う想定。
    UNSPECIFIEDは分類しない(できない)場合の既定値。REFERENCEは参考資料(PDF・DOCX・XLSX等)で、
    生成AIに渡す資料になる。新しい種類が加わったら、ここへ値を追加すること。"""

    UNSPECIFIED = "unspecified"
    REFERENCE = "reference"


class DatasetProvenance(BaseModel):
    """Datasetがシステムに入った機構(processのみ)の記録。以前は「アプリの
    内部処理が自動生成したDatasetにのみ存在し、手動インポートには無い」
    という、ブロックの有無で由来を区別する設計だったが、手動登録にも
    machine-readableな値(manually_registered)を持たせるようにしたため、
    全Datasetに常時存在する(存在有無ではなく値で区別する)。"""

    process: DatasetProvenanceProcess = DatasetProvenanceProcess.MANUALLY_REGISTERED
    parameters: dict[str, Any] = {}
    source_refs: list[DatasetSourceRef] = []


class DatasetHistoryEntry(BaseModel):
    updated_at: str
    message: str = ""


class DatasetColumnInfo(BaseModel):
    name: str
    type: Optional[str] = None
    description: Optional[str] = None


class DatasetInfo(BaseModel):
    # project.dbのdataset_registry(core.infra.store.dataset_registry_store)で
    # 発行される、不変のDataset識別子(UUID4文字列)。filenameはリネームで
    # 変わりうるため、システム内部の追跡・参照(source_refs等)にはこちらを
    # 使う。登録の無い(手動配置の)ファイルは
    # Noneになりうるが、API層がアクセスの都度自動採番して登録し直す
    # (core.infra.store.dataset_registry_store.get_or_create_file_id)ため、実質的には
    # 一度でもAPI経由でアクセスされたDatasetは必ず持つ。
    file_id: Optional[str] = None
    description: Optional[str] = None
    source: Optional[str] = None
    collected_at: Optional[str] = None
    tags: list[str] = []
    notes: Optional[str] = None
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    # Datasetが属するドラマ(QIDMのDomainに相当する概念として検討中。docs/future_design.md)。
    # 作成時点のスナップショットで、ドラマの題が後から変わっても更新しない
    drama_id: Optional[str] = None
    drama_title: Optional[str] = None
    # このDatasetがどんな種類のデータか(DatasetCategory参照)。
    # provenance.process(機構: manually_registered/system_derived)とは別軸の分類。
    dataset_category: DatasetCategory = DatasetCategory.UNSPECIFIED
    created_at: Optional[str] = None
    history: list[DatasetHistoryEntry] = []


class DatasetMetadata(BaseModel):
    protocol_version: str = "0.1.0"
    dataset: DatasetInfo = DatasetInfo()
    provenance: DatasetProvenance = DatasetProvenance()
    columns: list[DatasetColumnInfo] = []
