# core/infra/store/ai_build_store.py
"""
Build with AI(生成AIと相談しながら作品を作るパネル)の会話の記録(project.dbのai_build_messageテーブル)。

会話は作品ごとに1本で、各発言はどの工程(タブ。core.prompt.ai_build.step)での発言かを持つ。シーンごとの工程(Script)の発言は
どのシーンでの発言か(scene_id)も持つ。生成AIに渡す履歴と画面に出す会話は、今の工程(と今のシーン)の発言だけ。生成AIの発言は、返事・根拠・質問・注意(reply_json)と、提案を下書きへ重ねる部分YAML(patch_yaml)と、
提案の状態(pending=未反映・applied=反映済み・undone=取り消し済み)を持つ。

作品の正本のテーブル(core.infra.store.drama_model_store)は確定のたびに書き直すので、外部キーで結び付けない(作品のidで持つ)。
"""

import json
import os
import sqlite3
from datetime import UTC, datetime
from typing import Any, Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ai_build_message (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dramaturgy_id TEXT NOT NULL,
    step TEXT NOT NULL,
    scene_id TEXT,
    role TEXT NOT NULL,
    mode TEXT,
    text TEXT NOT NULL,
    reply_json TEXT,
    patch_yaml TEXT,
    proposal_status TEXT,
    applied_revision INTEGER,
    reference_file_ids TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ai_build_message_by_step ON ai_build_message (dramaturgy_id, step, scene_id, id);
"""

PENDING = "pending"
APPLIED = "applied"
UNDONE = "undone"


class StoredMessage:
    """scene_idはシーンごとの工程での発言のシーン(ほかの工程ではNone)。roleはuser(利用者)・assistant(生成AI)。replyは生成AIの返事の構造(返事・提案・根拠・質問・注意)の対応表。"""

    def __init__(
        self,
        id: int,
        dramaturgy_id: str,
        step: str,
        scene_id: Optional[str],
        role: str,
        mode: Optional[str],
        text: str,
        reply: Optional[dict[str, Any]],
        patch_yaml: Optional[str],
        proposal_status: Optional[str],
        applied_revision: Optional[int],
        reference_file_ids: list[str],
        created_at: str,
    ):
        self.id: int = id
        self.dramaturgy_id: str = dramaturgy_id
        self.step: str = step
        self.scene_id: Optional[str] = scene_id
        self.role: str = role
        self.mode: Optional[str] = mode
        self.text: str = text
        self.reply: Optional[dict[str, Any]] = reply
        self.patch_yaml: Optional[str] = patch_yaml
        self.proposal_status: Optional[str] = proposal_status
        self.applied_revision: Optional[int] = applied_revision
        self.reference_file_ids: list[str] = reference_file_ids
        self.created_at: str = created_at


def _now() -> str:
    return datetime.now(UTC).astimezone().isoformat()


def _connect(db_path: str) -> sqlite3.Connection:
    dirname = os.path.dirname(db_path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def _message(row: sqlite3.Row) -> StoredMessage:
    return StoredMessage(
        row["id"],
        row["dramaturgy_id"],
        row["step"],
        row["scene_id"],
        row["role"],
        row["mode"],
        row["text"],
        json.loads(row["reply_json"]) if row["reply_json"] else None,
        row["patch_yaml"],
        row["proposal_status"],
        row["applied_revision"],
        json.loads(row["reference_file_ids"] or "[]"),
        row["created_at"],
    )


def add_exchange(
    db_path: str,
    dramaturgy_id: str,
    step: str,
    scene_id: Optional[str],
    mode: str,
    user_text: str,
    reference_file_ids: list[str],
    reply_text: str,
    reply: dict[str, Any],
    patch_yaml: Optional[str],
) -> StoredMessage:
    """利用者の発言と生成AIの返事を、1つのトランザクションで記録する(生成AIの呼び出しが成功したときだけ呼ぶ)。
    提案(patch_yaml)があれば、生成AIの発言の提案の状態をpendingにする。生成AIの発言を返す。"""
    conn = _connect(db_path)
    try:
        with conn:
            now = _now()
            conn.execute(
                "INSERT INTO ai_build_message (dramaturgy_id, step, scene_id, role, mode, text, reference_file_ids, created_at) "
                "VALUES (?, ?, ?, 'user', ?, ?, ?, ?)",
                (dramaturgy_id, step, scene_id, mode, user_text, json.dumps(reference_file_ids), now),
            )
            cursor = conn.execute(
                "INSERT INTO ai_build_message "
                "(dramaturgy_id, step, scene_id, role, mode, text, reply_json, patch_yaml, proposal_status, created_at) "
                "VALUES (?, ?, ?, 'assistant', ?, ?, ?, ?, ?, ?)",
                (
                    dramaturgy_id,
                    step,
                    scene_id,
                    mode,
                    reply_text,
                    json.dumps(reply, ensure_ascii=False),
                    patch_yaml,
                    PENDING if patch_yaml else None,
                    now,
                ),
            )
            message_id = cursor.lastrowid
        return get_message(db_path, message_id)
    finally:
        conn.close()


def list_messages(
    db_path: str, dramaturgy_id: str, step: str, scene_id: Optional[str] = None
) -> list[StoredMessage]:
    """作品の、ある工程(シーンごとの工程ではそのシーン)の発言(古い順)。"""
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM ai_build_message WHERE dramaturgy_id = ? AND step = ? AND scene_id IS ? ORDER BY id",
            (dramaturgy_id, step, scene_id),
        ).fetchall()
        return [_message(row) for row in rows]
    finally:
        conn.close()


def get_message(db_path: str, message_id: int) -> StoredMessage:
    """発言(無ければKeyError)。"""
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT * FROM ai_build_message WHERE id = ?", (message_id,)).fetchone()
        if row is None:
            raise KeyError(f"発言 {message_id} がありません")
        return _message(row)
    finally:
        conn.close()


def set_proposal_status(
    db_path: str, message_id: int, status: str, applied_revision: Optional[int] = None
) -> StoredMessage:
    conn = _connect(db_path)
    try:
        with conn:
            conn.execute(
                "UPDATE ai_build_message SET proposal_status = ?, applied_revision = ? WHERE id = ?",
                (status, applied_revision, message_id),
            )
        return get_message(db_path, message_id)
    finally:
        conn.close()


def clear_messages(db_path: str, dramaturgy_id: str, step: str, scene_id: Optional[str] = None) -> int:
    """作品の、ある工程(シーンごとの工程ではそのシーン)の発言をすべて消す(Clear)。消した数を返す。"""
    conn = _connect(db_path)
    try:
        with conn:
            cursor = conn.execute(
                "DELETE FROM ai_build_message WHERE dramaturgy_id = ? AND step = ? AND scene_id IS ?",
                (dramaturgy_id, step, scene_id),
            )
        return cursor.rowcount
    finally:
        conn.close()
