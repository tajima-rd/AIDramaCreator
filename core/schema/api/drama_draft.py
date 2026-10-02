# core/schema/api/drama_draft.py
"""
作品モデルの下書き(core.service.api.drama_draft)のDTO。下書きの中身はモデル定義YAMLの形
(DramaturgyDefinition)で返し、Apply・直接編集・取り込みは部分YAML(モデル定義YAMLの形で、変えたい部分だけ)を
リクエストの本文そのものとして受け取る(docs/database_design.md「部分YAMLの重ね合わせ」)。
"""

from typing import Any, Optional

from pydantic import BaseModel


class DramaDraftCreateRequest(BaseModel):
    title: Optional[str] = None


class DramaDraftInfo(BaseModel):
    draft_id: str
    title: Optional[str] = None
    base_version: Optional[int] = None  # 元にした版(Noneは版が無い状態から)
    status: str  # open / confirmed / discarded
    created_at: str
    updated_at: str


class DramaDraftListResult(BaseModel):
    drafts: list[DramaDraftInfo]


class DramaDraftRevisionSummary(BaseModel):
    revision: int
    operation: str  # create / apply / edit / undo / import
    created_at: str


class DramaDraftRevisionListResult(BaseModel):
    revisions: list[DramaDraftRevisionSummary]


class DramaDraftChangeResult(BaseModel):
    """Apply・直接編集・取り込み・Undoの結果。revisionは積んだ履歴の番号。"""

    revision: int


class DramaDraftImportPathRequest(BaseModel):
    """サーバーの手元にあるモデル定義YAMLのファイルか、分割したファイルを置いたディレクトリを取り込む。"""

    path: str
    replace: bool = False


class DramaDraftGeodataImportRequest(BaseModel):
    """場所の地図(KML・KMZ・GeoPackage)を作品に取り込む(2026-10-02)。APIはYAMLでやり取りするため、ファイルの中身はbase64で渡す。
    形式はfilenameの拡張子(.kml・.xml・.kmz・.gpkg)で決める。"""

    dramaturgy_id: str
    filename: str
    content_base64: str


class DramaDraftGeodataImportResult(BaseModel):
    """地図の取り込みの結果。補助情報(場所・移動以外の層)があれば、作品に割り当てたDataset(GeoPackage)として保存する。"""

    revision: int
    locations_created: int
    locations_updated: int
    site_flows_created: int
    site_flows_updated: int
    auxiliary_layers: dict[str, int] = {}  # 補助情報の層の名前→地物の数
    auxiliary_file_id: Optional[str] = None  # 補助情報を保存したDatasetのfile_id
    auxiliary_filename: Optional[str] = None


class DramaDraftMapLocation(BaseModel):
    """地図の画面の場所(Location)。geometryはGeoJSONの形(WGS84、経度・緯度の順)。idが無ければ新しい場所。
    used_in_scenesは読み出しだけ(作品のシーンが使っているか)。"""

    id: Optional[str] = None
    name: str
    address: Optional[str] = None
    instruction: Optional[str] = None
    description: Optional[str] = None
    geometry: Optional[dict[str, Any]] = None
    used_in_scenes: bool = False


class DramaDraftMapSiteFlow(BaseModel):
    """地図の画面の移動(SiteFlow)。geometryはGeoJSONの線。origin_id・destination_idは読み出しだけ
    (保存では線の始点・終点を含む場所の面から決める)。"""

    id: Optional[str] = None
    name: Optional[str] = None
    direction: Optional[str] = None  # forward・backward・both
    geometry: Optional[dict[str, Any]] = None
    origin_id: Optional[str] = None
    destination_id: Optional[str] = None


class DramaDraftMapAuxiliaryFeature(BaseModel):
    geometry: Optional[dict[str, Any]] = None
    properties: dict[str, Any] = {}


class DramaDraftMapAuxiliaryLayer(BaseModel):
    """補助情報(作品に割り当てたGeoPackageのDataset)の層。地図の画面では表示だけ。"""

    dataset_filename: str
    layer: str
    features: list[DramaDraftMapAuxiliaryFeature]


class DramaDraftMapResult(BaseModel):
    """下書きの作品の地図(2026-10-02)。作品が参照する場所・移動(形の無いものも含む)と、補助情報。"""

    dramaturgy_id: str
    dramaturgy_title: str = ""
    locations: list[DramaDraftMapLocation]
    site_flows: list[DramaDraftMapSiteFlow]
    auxiliary_layers: list[DramaDraftMapAuxiliaryLayer] = []
    warnings: list[str] = []


class DramaDraftMapSaveRequest(BaseModel):
    """地図の画面の状態(形のある場所・移動のすべて)を作品に保存する。送らなかった場所・移動は作品の参照から外す
    (形の無いものは残す)。"""

    dramaturgy_id: str
    locations: list[DramaDraftMapLocation]
    site_flows: list[DramaDraftMapSiteFlow] = []


class DramaDraftMapSaveResult(BaseModel):
    revision: int
    locations_created: int
    locations_updated: int
    site_flows_created: int
    site_flows_updated: int


class DramaDraftConfirmRequest(BaseModel):
    note: Optional[str] = None


class DramaDraftConfirmResult(BaseModel):
    version: int  # 確定でできた版の番号
