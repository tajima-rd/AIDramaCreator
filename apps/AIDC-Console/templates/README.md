# 場所の雛形

シーンの場所(`Location`)と、Locationどうしの移動(`SiteFlow`)を描くための雛形(2026-10-02)。
`location_template.kml`(Google マイマップ等)と`location_template.gpkg`(QGIS等)は同じ構成。
座標はWGS84(EPSG:4326)。Dramaturgy EditorのLocationsタブ(Import KML / GeoPackage...)で作品に取り込む
(扱いは[architecture.md](../../../docs/architecture.md) 7節「場所の地図の取り込み」)。

| 層 | KMLのフォルダ | GeoPackageの層 | 形 | 属性 |
| --- | --- | --- | --- | --- |
| Location | Location | `location` | 面 | `id`・`key`・`name`・`address`・`instruction`・`description`(`Location`の属性。形は面そのもの) |
| SiteFlow | SiteFlow | `site_flow` | 線 | `name`・`direction` |
| 補助情報 | 上の2つ以外のすべてのフォルダ(雛形では`補助情報`) | 上の2つ以外のすべての層(雛形では`reference_point`・`reference_line`・`reference_polygon`) | 点・線・面 | 自由(雛形では`name`・`description`だけ) |

- **Location**: 1つの面が、シーンの場所(`Location`)1つ(Locatoneでは再生エリアに当たる)。`instruction`はそこで案内すること、`description`はその場所の事実。
- **SiteFlow**: Locationどうしの移動。線の始点を含むLocationと、終点を含むLocationをつなぐ。途中の頂点は道筋で、つながりには関係しない。
  `direction`は線を引いた向きに対する移動の向きで、`forward`(始点のLocation→終点のLocation)・`backward`(終点→始点)・`both`(双方向)。
- **補助情報**: リフト・施設・乗降場所等、位置関係の説明に使う地物。フォルダ・層の名前、形、属性の決まりは無い
  (Google マイマップはフォルダを入れ子にできないため、LocationとSiteFlow以外はすべて補助情報とみなす)。
- 記入例は`apps/sample_data/ハチ北スキー場ガイド/ハチ北スキー場.kml`。
