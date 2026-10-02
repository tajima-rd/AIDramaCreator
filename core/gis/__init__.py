# core/gis
"""
地理情報(GIS)の汎用ライブラリ(2026-10-02ユーザー決定)。形はWKTの文字列で受け渡し、座標はWGS84(EPSG:4326)、経度・緯度の順。

他のプロジェクトでも使えるよう、core.genaiと同じく、このパッケージの外(core.model・core.infra等)をimportしない
(tests/core/test_gis_independence.pyで確かめる)。依存はshapelyだけで、GDALは要らない。場所(Location)・移動(SiteFlow)等の
AIDCの意味づけは使う側(core.infra・core.service)が持つ。

- geometry: WKTの検査・正規化と、GeoJSON(地図の画面とのやり取り)との変換
- feature: 地物(形と属性の組)の型
- io/: ファイル形式の読み書き(geopackage=GeoPackage、kml=KML・KMZ)
- analysis/: 空間の関係(containment=点を含む面)
"""
