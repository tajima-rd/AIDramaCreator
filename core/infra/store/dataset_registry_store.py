# core/infra/store/dataset_registry_store.py
"""
プロジェクトのDB(project.db)の`dataset_registry`テーブル(file_id/filename/drama_id/imported_at)の読み書き。

file_id(UUID4文字列)は、filenameに依存せずDatasetを追跡するための不変の
識別子。filenameはリネームで変わりうるためAPI/フロントの主キーには
向かないが、データ本体は実際にfilenameでdatasets_dir配下に存在するため、
file_id -> filenameの解決はこのモジュールが一元的に担う。

drama_idはDatasetが属するドラマ(QIDMのDomainに相当する概念として検討中。docs/future_design.md)。
ドラマの定義がまだ無いため、現状は常にNone(未割当)で登録する。

QIDMではdomain.dbのテーブルだったものを、暫定的にproject.dbへ移した(docs/future_design.md「SQLite」)。
各関数はdb_path(project.dbのパス)を第1引数に取り、接続するだけでスキーマ付きの空DBを作る。
"""

import os
import sqlite3
from datetime import UTC, datetime

from core.model.identifier import new_id

_SCHEMA = """
CREATE TABLE IF NOT EXISTS dataset_registry (
    file_id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    drama_id TEXT,
    imported_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(UTC).astimezone().isoformat()


def ensure_schema(db_path: str) -> None:
    """db_pathにdataset_registryテーブルが無ければ作る(DBファイルも無ければ作る)。"""
    dirname = os.path.dirname(db_path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()


def register_dataset(db_path: str, filename: str, drama_id: str | None) -> str:
    """
    dataset_registryへ(file_id, filename, drama_id)を記録し、そのfile_idを
    返す。同名ファイルが既に登録されていれば、そのfile_idを引き継いだ上で
    エントリを更新する(再インポート時にfile_idが変わらないようにするため)。
    未登録の場合は新規にfile_idを発行する。
    """
    ensure_schema(db_path)
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT file_id FROM dataset_registry WHERE filename = ?", (filename,))
        existing = cursor.fetchone()
        file_id = existing[0] if existing else new_id()
        cursor.execute("DELETE FROM dataset_registry WHERE filename = ?", (filename,))
        cursor.execute(
            "INSERT INTO dataset_registry (file_id, filename, drama_id, imported_at) "
            "VALUES (?, ?, ?, ?)",
            (file_id, filename, drama_id, _now()),
        )
        conn.commit()
        return file_id
    finally:
        conn.close()


def get_or_create_file_id(db_path: str, filename: str) -> str:
    """
    filenameに対応するfile_idを返す。registryにエントリが無い場合
    (手動で配置したファイル等)は、drama_id無しで新規登録してfile_idを発行する
    (自己修復的な登録。一覧に表示されるだけで登録が一度も無かったファイルを、
    最初にアクセスされた時点で登録する)。
    """
    ensure_schema(db_path)
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT file_id FROM dataset_registry WHERE filename = ?", (filename,))
        row = cursor.fetchone()
        if row is not None:
            return row[0]
    finally:
        conn.close()
    return register_dataset(db_path, filename, None)


def resolve_filename(db_path: str, file_id: str) -> str | None:
    """file_idからfilenameを引く。見つからなければNone。"""
    ensure_schema(db_path)
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT filename FROM dataset_registry WHERE file_id = ?", (file_id,))
        row = cursor.fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def list_dataset_entries(db_path: str) -> list[dict]:
    """dataset_registryの全エントリを読む。未記録のプロジェクトでは空リスト。"""
    ensure_schema(db_path)
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT file_id, filename, drama_id, imported_at FROM dataset_registry")
        return [
            {"file_id": file_id, "filename": filename, "drama_id": drama_id, "imported_at": imported_at}
            for file_id, filename, drama_id, imported_at in cursor.fetchall()
        ]
    finally:
        conn.close()


def unregister_dataset(db_path: str, filename: str) -> None:
    """dataset_registryから該当エントリを削除する。登録が無ければ何もしない。"""
    ensure_schema(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DELETE FROM dataset_registry WHERE filename = ?", (filename,))
        conn.commit()
    finally:
        conn.close()


def rename_registered_dataset(db_path: str, old_filename: str, new_filename: str) -> None:
    """
    dataset_registry内、該当エントリのfilenameを差し替える
    (file_id/drama_id/imported_atは維持する)。登録が無ければ何もしない。
    """
    ensure_schema(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE dataset_registry SET filename = ? WHERE filename = ?",
            (new_filename, old_filename),
        )
        conn.commit()
    finally:
        conn.close()
