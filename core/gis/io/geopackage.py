# core/gis/io/geopackage.py
"""
GeoPackage(OGC GeoPackage 1.4。中身はSQLite)の読み書きの部品。既存のSQLiteのDBをGeoPackageとしても読めるようにすること
(ensure_geopackage)、GeoPackageのファイルからの地物の読み出し(read_feature_tables)、地物の層を新しいファイルに書くこと
(write_feature_layers)に使う。GDALを使わず標準のsqlite3とshapelyだけで扱う。

- GeoPackageの印(application_id・user_version)と、管理の表(gpkg_spatial_ref_sys・gpkg_contents・gpkg_geometry_columns)を作る。
  gpkg_contentsに載せた表だけがGISの道具から見え、ほかの表はそのまま。
- 空間索引(R-tree)は付けない(GDALが作る索引のトリガーはSpatiaLiteの関数を使い、標準のsqlite3から書き込めなくなるため)。
- 形の列の値はGeoPackageのBLOB(ヘッダー+WKB)。形(WKT)との変換はencode_geometry・decode_geometry。
  座標系はWGS84(EPSG:4326)だけを使う。
"""

import os
import sqlite3
import struct
from typing import Optional

import shapely

from ..feature import Feature
from ..geometry import parse_wkt, to_wkt

SRS_ID = 4326
_APPLICATION_ID = 0x47504B47  # "GPKG"
_USER_VERSION = 10400  # GeoPackage 1.4.0

_WGS84_DEFINITION = (
    'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],'
    'AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],'
    'UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],AXIS["Latitude",NORTH],AXIS["Longitude",EAST],'
    'AUTHORITY["EPSG","4326"]]'
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS gpkg_spatial_ref_sys (
    srs_name TEXT NOT NULL,
    srs_id INTEGER PRIMARY KEY,
    organization TEXT NOT NULL,
    organization_coordsys_id INTEGER NOT NULL,
    definition TEXT NOT NULL,
    description TEXT
);
CREATE TABLE IF NOT EXISTS gpkg_contents (
    table_name TEXT NOT NULL PRIMARY KEY,
    data_type TEXT NOT NULL,
    identifier TEXT UNIQUE,
    description TEXT DEFAULT '',
    last_change DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    min_x DOUBLE,
    min_y DOUBLE,
    max_x DOUBLE,
    max_y DOUBLE,
    srs_id INTEGER,
    CONSTRAINT fk_gc_r_srs_id FOREIGN KEY (srs_id) REFERENCES gpkg_spatial_ref_sys(srs_id)
);
CREATE TABLE IF NOT EXISTS gpkg_geometry_columns (
    table_name TEXT NOT NULL,
    column_name TEXT NOT NULL,
    geometry_type_name TEXT NOT NULL,
    srs_id INTEGER NOT NULL,
    z TINYINT NOT NULL,
    m TINYINT NOT NULL,
    CONSTRAINT pk_geom_cols PRIMARY KEY (table_name, column_name),
    CONSTRAINT uk_gc_table_name UNIQUE (table_name),
    CONSTRAINT fk_gc_tn FOREIGN KEY (table_name) REFERENCES gpkg_contents(table_name),
    CONSTRAINT fk_gc_srs FOREIGN KEY (srs_id) REFERENCES gpkg_spatial_ref_sys(srs_id)
);
"""

# 形のBLOBのヘッダーの、包む範囲(envelope)の種類→その長さ(バイト)
_ENVELOPE_SIZES = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}


def ensure_geopackage(conn: sqlite3.Connection, feature_tables: dict[str, tuple[str, str]]) -> None:
    """
    GeoPackageの印と管理の表を作り、feature_tables(表の名前→(形の列の名前, 形の種類の名前(GEOMETRY・LINESTRING等)))を
    地物の表として登録する(すでにあれば何もしない)。表そのものは呼ぶ側が作る。
    """
    conn.execute(f"PRAGMA application_id = {_APPLICATION_ID}")
    conn.execute(f"PRAGMA user_version = {_USER_VERSION}")
    conn.executescript(_SCHEMA)
    conn.executemany(
        "INSERT OR IGNORE INTO gpkg_spatial_ref_sys VALUES (?, ?, ?, ?, ?, ?)",
        [
            ("Undefined cartesian SRS", -1, "NONE", -1, "undefined", "undefined cartesian coordinate reference system"),
            ("Undefined geographic SRS", 0, "NONE", 0, "undefined", "undefined geographic coordinate reference system"),
            ("WGS 84 geodetic", SRS_ID, "EPSG", 4326, _WGS84_DEFINITION, "longitude/latitude coordinates in decimal degrees on the WGS 84 spheroid"),
        ],
    )
    for table, (column, geometry_type) in feature_tables.items():
        conn.execute(
            "INSERT OR IGNORE INTO gpkg_contents (table_name, data_type, identifier, srs_id) VALUES (?, 'features', ?, ?)",
            (table, table, SRS_ID),
        )
        conn.execute(
            "INSERT OR IGNORE INTO gpkg_geometry_columns VALUES (?, ?, ?, ?, 0, 0)",
            (table, column, geometry_type, SRS_ID),
        )


def encode_geometry(wkt: Optional[str]) -> Optional[bytes]:
    """形(WKT)を、GeoPackageのBLOB(リトルエンディアン、XYの包む範囲付き)にする。"""
    if wkt is None:
        return None
    geometry = parse_wkt(wkt, "形")
    min_x, min_y, max_x, max_y = geometry.bounds
    flags = 0b0000_0011  # リトルエンディアン(bit0)、包む範囲はXY(bit1-3が1)
    header = b"GP" + struct.pack("<BBi4d", 0, flags, SRS_ID, min_x, max_x, min_y, max_y)
    return header + shapely.to_wkb(geometry, byte_order=1, flavor="iso")


def decode_geometry(blob: Optional[bytes]) -> Optional[str]:
    """GeoPackageのBLOBを、形(WKT)にする。"""
    if blob is None:
        return None
    if blob[:2] != b"GP":
        raise ValueError("GeoPackageの形のBLOBではありません")
    flags = blob[3]
    if flags & 0b0010_0000:
        raise ValueError("拡張された形(ExtendedGeoPackageBinary)は読めません")
    if flags & 0b0001_0000:
        return None  # 空の形
    envelope = _ENVELOPE_SIZES[(flags >> 1) & 0b111]
    return to_wkt(shapely.from_wkb(bytes(blob[8 + envelope :])))


def _quote(name: str) -> str:
    """SQLの識別子として引用する(日本語の層の名前等)。"""
    return '"' + name.replace('"', '""') + '"'


def read_feature_tables(path: str) -> dict[str, list[Feature]]:
    """
    GeoPackageのファイルの地物の表(gpkg_contentsのfeatures)をすべて読む。戻り値は 表の名前→[(形(WKT。無ければNone), 属性)]。
    属性は形の列と整数の主キー(fid)を除いたすべての列(値はSQLiteの値のまま)。並びは行の順(rowid)。
    """
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        try:
            tables = conn.execute(
                "SELECT c.table_name, g.column_name FROM gpkg_contents c "
                "JOIN gpkg_geometry_columns g ON g.table_name = c.table_name "
                "WHERE c.data_type = 'features' ORDER BY c.rowid"
            ).fetchall()
        except sqlite3.DatabaseError as e:
            raise ValueError(f"GeoPackageとして読めません: {e}") from None
        result: dict[str, list[Feature]] = {}
        for table, geometry_column in tables:
            info = conn.execute(f"PRAGMA table_info({_quote(table)})").fetchall()
            primary = {row[1] for row in info if row[5] and row[2].upper() == "INTEGER"}
            columns = [row[1] for row in info if row[1] != geometry_column and row[1] not in primary]
            select = ", ".join(_quote(c) for c in [geometry_column, *columns])
            features = []
            for row in conn.execute(f"SELECT {select} FROM {_quote(table)} ORDER BY rowid"):
                features.append((decode_geometry(row[0]), dict(zip(columns, row[1:]))))
            result[table] = features
        return result
    finally:
        conn.close()


def write_feature_layers(path: str, layers: dict[str, list[Feature]]) -> None:
    """
    地物の層(層の名前→[(形(WKT), 属性)])を、新しいGeoPackageのファイルに書く(pathに既にあれば作り直す)。
    属性は層ごとに現れた名前をすべて文字列の列にする。形の種類はGEOMETRY(点・線・面が混ざってよい)。
    """
    if os.path.exists(path):
        os.remove(path)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(_SCHEMA)
        columns_by_layer = {}
        for layer, features in layers.items():
            columns: list[str] = []
            for _, attributes in features:
                for name in attributes:
                    if name not in columns and name.lower() not in ("fid", "geom"):
                        columns.append(name)
            columns_by_layer[layer] = columns
            definitions = "".join(f", {_quote(c)} TEXT" for c in columns)
            conn.execute(
                f"CREATE TABLE {_quote(layer)} (fid INTEGER PRIMARY KEY AUTOINCREMENT, geom BLOB{definitions})"
            )
        ensure_geopackage(conn, {layer: ("geom", "GEOMETRY") for layer in layers})
        for layer, features in layers.items():
            columns = columns_by_layer[layer]
            names = ", ".join(_quote(c) for c in ["geom", *columns])
            marks = ", ".join("?" for _ in range(len(columns) + 1))
            for wkt, attributes in features:
                values = [None if attributes.get(c) is None else str(attributes[c]) for c in columns]
                conn.execute(
                    f"INSERT INTO {_quote(layer)} ({names}) VALUES ({marks})",
                    [encode_geometry(wkt), *values],
                )
        conn.commit()
    finally:
        conn.close()
