# core/infra/store/drama_version_store.py
"""
プロジェクトのDB(project.db)にある、作品モデルの版と下書きのテーブルの読み書き(docs/database_design.md「A. 版と下書き」)。

- model_version: ③ 版。下書きを確定した時点の、プロジェクトの作品モデル全体の写し(モデル定義YAML)。
- draft: 下書き。確定した版(base_version)を元に作る。statusはopen・confirmed・discarded。
- draft_revision: ② 下書きの履歴。作成・Apply・直接編集・Undo・取り込みのたびに、作品モデル全体の写しを1行ずつ積む。

各関数は接続を受け取り、コミットしない(手順はcore.service.process.edit.drama_draft_editor。確定は正本の書き換えと
同じトランザクションで行う)。
"""

import sqlite3
from datetime import UTC, datetime
from typing import Optional

from core.model.identifier import new_id

DRAFT_STATUSES = ("open", "confirmed", "discarded")
REVISION_OPERATIONS = ("create", "apply", "edit", "undo", "import")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS model_version (
    version INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    draft_id TEXT,
    note TEXT,
    snapshot TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS draft (
    id TEXT PRIMARY KEY,
    title TEXT,
    base_version INTEGER REFERENCES model_version(version),
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS draft_revision (
    draft_id TEXT NOT NULL REFERENCES draft(id) ON DELETE CASCADE,
    revision INTEGER NOT NULL,
    operation TEXT NOT NULL,
    created_at TEXT NOT NULL,
    snapshot TEXT NOT NULL,
    PRIMARY KEY (draft_id, revision)
);
"""


class DraftNotFoundError(LookupError):
    """指定したdraft_idの下書きが無い。"""


class VersionNotFoundError(LookupError):
    """指定した番号の版が無い。"""


class VersionInfo:
    """版の管理情報(写しを除く)。"""

    def __init__(self, version: int, created_at: str, draft_id: Optional[str], note: Optional[str]):
        self.version: int = version
        self.created_at: str = created_at
        self.draft_id: Optional[str] = draft_id
        self.note: Optional[str] = note


class DraftInfo:
    """下書きの管理情報。"""

    def __init__(
        self,
        id: str,
        title: Optional[str],
        base_version: Optional[int],
        status: str,
        created_at: str,
        updated_at: str,
    ):
        self.id: str = id
        self.title: Optional[str] = title
        self.base_version: Optional[int] = base_version
        self.status: str = status
        self.created_at: str = created_at
        self.updated_at: str = updated_at


class RevisionInfo:
    """下書きの履歴の1行の管理情報(写しを除く)。"""

    def __init__(self, revision: int, operation: str, created_at: str):
        self.revision: int = revision
        self.operation: str = operation
        self.created_at: str = created_at


def _now() -> str:
    return datetime.now(UTC).astimezone().isoformat()


def ensure_schema(conn: sqlite3.Connection) -> None:
    """版と下書きのテーブルが無ければ作る。"""
    conn.executescript(_SCHEMA)


# ---- 版 ----


def current_version(conn: sqlite3.Connection) -> Optional[int]:
    """最新の版の番号。版が無ければNone。"""
    row = conn.execute("SELECT MAX(version) FROM model_version").fetchone()
    return row[0]


def add_version(
    conn: sqlite3.Connection, snapshot: str, draft_id: Optional[str], note: Optional[str]
) -> int:
    """版を1つ足し、その番号(1からの連番)を返す。"""
    version = (current_version(conn) or 0) + 1
    conn.execute(
        "INSERT INTO model_version (version, created_at, draft_id, note, snapshot) "
        "VALUES (?, ?, ?, ?, ?)",
        (version, _now(), draft_id, note, snapshot),
    )
    return version


def list_versions(conn: sqlite3.Connection) -> list[VersionInfo]:
    """版の一覧(古い順)。"""
    return [
        VersionInfo(*row)
        for row in conn.execute(
            "SELECT version, created_at, draft_id, note FROM model_version ORDER BY version"
        )
    ]


def read_version_snapshot(conn: sqlite3.Connection, version: int) -> str:
    """版の写し(モデル定義YAML)。"""
    row = conn.execute(
        "SELECT snapshot FROM model_version WHERE version = ?", (version,)
    ).fetchone()
    if row is None:
        raise VersionNotFoundError(f"版 {version} はありません")
    return row[0]


# ---- 下書き ----


def create_draft(
    conn: sqlite3.Connection, title: Optional[str], base_version: Optional[int]
) -> str:
    """下書きを作り(status=open。履歴は空)、そのidを返す。"""
    draft_id = new_id()
    now = _now()
    conn.execute(
        "INSERT INTO draft (id, title, base_version, status, created_at, updated_at) "
        "VALUES (?, ?, ?, 'open', ?, ?)",
        (draft_id, title, base_version, now, now),
    )
    return draft_id


def read_draft(conn: sqlite3.Connection, draft_id: str) -> DraftInfo:
    row = conn.execute(
        "SELECT id, title, base_version, status, created_at, updated_at FROM draft WHERE id = ?",
        (draft_id,),
    ).fetchone()
    if row is None:
        raise DraftNotFoundError(f"下書き {draft_id} はありません")
    return DraftInfo(*row)


def list_drafts(conn: sqlite3.Connection, status: Optional[str] = None) -> list[DraftInfo]:
    """下書きの一覧(作った順)。statusを渡せば、その状態のものだけ。"""
    sql = "SELECT id, title, base_version, status, created_at, updated_at FROM draft"
    params: tuple = ()
    if status is not None:
        sql += " WHERE status = ?"
        params = (status,)
    return [DraftInfo(*row) for row in conn.execute(sql + " ORDER BY rowid", params)]


def set_draft_status(conn: sqlite3.Connection, draft_id: str, status: str) -> None:
    if status not in DRAFT_STATUSES:
        raise ValueError(f"下書きの状態 '{status}' はありません")
    read_draft(conn, draft_id)
    conn.execute(
        "UPDATE draft SET status = ?, updated_at = ? WHERE id = ?", (status, _now(), draft_id)
    )


def add_revision(conn: sqlite3.Connection, draft_id: str, operation: str, snapshot: str) -> int:
    """下書きの履歴に1行を積み、その番号(作成時が0)を返す。"""
    if operation not in REVISION_OPERATIONS:
        raise ValueError(f"下書きの操作 '{operation}' はありません")
    read_draft(conn, draft_id)
    row = conn.execute(
        "SELECT MAX(revision) FROM draft_revision WHERE draft_id = ?", (draft_id,)
    ).fetchone()
    revision = row[0] + 1 if row[0] is not None else 0
    now = _now()
    conn.execute(
        "INSERT INTO draft_revision (draft_id, revision, operation, created_at, snapshot) "
        "VALUES (?, ?, ?, ?, ?)",
        (draft_id, revision, operation, now, snapshot),
    )
    conn.execute("UPDATE draft SET updated_at = ? WHERE id = ?", (now, draft_id))
    return revision


def list_revisions(conn: sqlite3.Connection, draft_id: str) -> list[RevisionInfo]:
    """下書きの履歴(古い順)。"""
    read_draft(conn, draft_id)
    return [
        RevisionInfo(*row)
        for row in conn.execute(
            "SELECT revision, operation, created_at FROM draft_revision "
            "WHERE draft_id = ? ORDER BY revision",
            (draft_id,),
        )
    ]


def read_revision_snapshot(
    conn: sqlite3.Connection, draft_id: str, revision: Optional[int] = None
) -> str:
    """下書きの履歴の写し(モデル定義YAML)。revisionを省略すれば最新(今の下書きの中身)。"""
    read_draft(conn, draft_id)
    if revision is None:
        row = conn.execute(
            "SELECT snapshot FROM draft_revision WHERE draft_id = ? ORDER BY revision DESC LIMIT 1",
            (draft_id,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT snapshot FROM draft_revision WHERE draft_id = ? AND revision = ?",
            (draft_id, revision),
        ).fetchone()
    if row is None:
        raise DraftNotFoundError(f"下書き {draft_id} の履歴 {revision} はありません")
    return row[0]
