# core/service/process/edit/drama_draft_editor.py
"""
作品モデル(core.model.drama)の下書きと版の手順(docs/architecture.md 7節「作品モデルのDB」)。

- 正本(project.dbの作品のテーブル)を変える経路は、下書きの確定(confirm_draft)だけ。YAMLの取り込みも、下書きに
  取り込んで(import_yaml・import_definition)から確定する。
- Apply・直接編集・取り込みは、部分YAMLを下書きの今の中身に重ねる(core.infra.io.model_definition_patch。
  docs/database_design.md「部分YAMLの重ね合わせ」)。取り込みはreplaceで中身全体を置き換えることもできる。
- 下書きは、確定した最新の版を元に作る。Apply・直接編集・取り込み・Undoのたびに、作品モデル全体の写し(モデル定義YAML)を
  下書きの履歴に1行ずつ積む。Undoは1つ前と同じ内容を新しい行として積む(履歴は消さない。QIDMのdomain_draft_editorと同じ)。
- 確定=版の作成。正本を書き直し、版を1つ足し、下書きをconfirmedにする(1つのトランザクション)。下書きの元にした版が
  今の版と違えば、確定を拒否する(DraftConflictError。作り直してもらう)。

写しは、組み立て直したモデルから書き出したもの(model_definition_to_yaml)。idの無い要素にはここでidが付き、以後の履歴・版・
正本で同じidを保つ。エージェントは対象外(含むYAMLはValueError)。

各関数はproject.dbのパスを受け取る(QIDMの「DBのパス単位で動く内部の処理」)。
"""

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Union

from core.infra.io.model_definition_patch import patch_spec
from core.infra.io.model_definition_reader import (
    ModelDefinition,
    build_model_definition_from_spec,
    build_model_definition_from_yaml,
    definition_files,
    load_documents,
    merge_documents,
)
from core.infra.io.model_definition_writer import model_definition_to_yaml
from core.infra.store import drama_model_store, drama_version_store
from core.infra.store.drama_version_store import DraftInfo, RevisionInfo, VersionInfo


class DraftConflictError(ValueError):
    """下書きの元にした版のあとに、別の下書きが確定されている(確定できない)。"""


@contextmanager
def _connect(db_path: str) -> Iterator[sqlite3.Connection]:
    """project.dbにつなぎ(無ければ作る)、作品・版・下書きのテーブルをそろえる。ブロックを抜けるとコミットする
    (例外ならロールバック)。"""
    dirname = os.path.dirname(db_path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        drama_model_store.ensure_schema(conn)
        drama_version_store.ensure_schema(conn)
        with conn:
            yield conn
    finally:
        conn.close()


def _snapshot(definition: ModelDefinition) -> str:
    if definition.agents:
        raise ValueError("エージェント(agents)は下書きに入れられません(対象はcore.model.dramaだけ)")
    return model_definition_to_yaml(definition)


def _require_open(conn: sqlite3.Connection, draft_id: str) -> DraftInfo:
    draft = drama_version_store.read_draft(conn, draft_id)
    if draft.status != "open":
        raise ValueError(
            f"下書き {draft_id} は{draft.status}です(変更・確定できるのはopenの下書きだけ)"
        )
    return draft


# ---- 正本と版 ----


def load_model(db_path: str) -> ModelDefinition:
    """正本(確定した最新の作品モデル全体)。"""
    with _connect(db_path) as conn:
        return drama_model_store.read_model(conn)


def current_version(db_path: str) -> Optional[int]:
    """確定した最新の版の番号。まだ確定が無ければNone。"""
    with _connect(db_path) as conn:
        return drama_version_store.current_version(conn)


def list_versions(db_path: str) -> list[VersionInfo]:
    with _connect(db_path) as conn:
        return drama_version_store.list_versions(conn)


def version_yaml(db_path: str, version: int) -> str:
    """版の写し(モデル定義YAML)。"""
    with _connect(db_path) as conn:
        return drama_version_store.read_version_snapshot(conn, version)


# ---- 下書き ----


def create_draft(db_path: str, title: Optional[str] = None) -> DraftInfo:
    """確定した最新の版を元に下書きを作る(版が無ければ空の作品モデルから)。"""
    with _connect(db_path) as conn:
        base_version = drama_version_store.current_version(conn)
        snapshot = (
            drama_version_store.read_version_snapshot(conn, base_version)
            if base_version is not None
            else _snapshot(ModelDefinition())
        )
        draft_id = drama_version_store.create_draft(conn, title, base_version)
        drama_version_store.add_revision(conn, draft_id, "create", snapshot)
        return drama_version_store.read_draft(conn, draft_id)


def list_drafts(db_path: str, status: Optional[str] = None) -> list[DraftInfo]:
    with _connect(db_path) as conn:
        return drama_version_store.list_drafts(conn, status)


def read_draft(db_path: str, draft_id: str) -> DraftInfo:
    with _connect(db_path) as conn:
        return drama_version_store.read_draft(conn, draft_id)


def list_revisions(db_path: str, draft_id: str) -> list[RevisionInfo]:
    with _connect(db_path) as conn:
        return drama_version_store.list_revisions(conn, draft_id)


def draft_yaml(db_path: str, draft_id: str, revision: Optional[int] = None) -> str:
    """下書きの中身(モデル定義YAML)。revisionを渡せば、履歴のその行。"""
    with _connect(db_path) as conn:
        return drama_version_store.read_revision_snapshot(conn, draft_id, revision)


def load_draft_model(db_path: str, draft_id: str) -> ModelDefinition:
    """下書きの中身を組み立てたもの。"""
    return build_model_definition_from_yaml(draft_yaml(db_path, draft_id))


def _documents(yaml_texts: tuple[str, ...]) -> list[dict]:
    documents: list[dict] = []
    for text in yaml_texts:
        documents.extend(load_documents(text))
    return documents


def _push(
    db_path: str, draft_id: str, operation: str, documents: list[dict], replace: bool = False
) -> int:
    """
    部分YAMLを下書きの今の中身に重ね(replaceなら、中身をそれで置き換え)、組み立て直して検証してから履歴に積む。
    履歴の番号を返す。複数の文書は、分割ファイルと同じ規則で1つにまとめてから重ねる(分割した文書は、属する作品・幕を
    書かないことがあるため。まとめるときnullは無視されるので、値を消すには1つの文書で渡す)。
    """
    patch = documents[0] if len(documents) == 1 else merge_documents(documents)
    with _connect(db_path) as conn:
        _require_open(conn, draft_id)
        if replace:
            spec = patch or {}
        else:
            base = load_documents(drama_version_store.read_revision_snapshot(conn, draft_id))
            spec = patch_spec(base[0] if base else {}, [patch])
        snapshot = _snapshot(build_model_definition_from_spec(spec))
        return drama_version_store.add_revision(conn, draft_id, operation, snapshot)


def apply_to_draft(db_path: str, draft_id: str, *yaml_texts: str) -> int:
    """生成AIの提案を反映する(Apply)。部分YAMLを下書きの中身に重ねる。履歴の番号を返す。"""
    return _push(db_path, draft_id, "apply", _documents(yaml_texts))


def edit_draft(db_path: str, draft_id: str, *yaml_texts: str) -> int:
    """利用者の直接編集を保存する。部分YAMLを下書きの中身に重ねる。履歴の番号を返す。"""
    return _push(db_path, draft_id, "edit", _documents(yaml_texts))


def import_yaml(db_path: str, draft_id: str, *yaml_texts: str, replace: bool = False) -> int:
    """
    モデル定義YAMLの文字列(分割したものは複数)を取り込む。既定は下書きの中身に重ね、replaceなら中身をそれで置き換える。
    履歴の番号を返す。
    """
    return _push(db_path, draft_id, "import", _documents(yaml_texts), replace)


def import_definition(
    db_path: str, draft_id: str, path: Union[str, Path], replace: bool = False
) -> int:
    """モデル定義YAMLのファイル、または分割したファイルを置いたディレクトリを取り込む(重ね方はimport_yamlと同じ)。"""
    documents: list[dict] = []
    for file in definition_files(path):
        documents.extend(load_documents(file.read_text(encoding="utf-8")))
    return _push(db_path, draft_id, "import", documents, replace)


def undo(db_path: str, draft_id: str) -> int:
    """
    最後の変更(Apply・直接編集・取り込み・Undo)を1つ戻す。履歴からは消さず、1つ前と同じ内容を新しい行(undo)として積む。
    続けてUndoすると、さらに前の変更まで遡る(Undoの行を飛ばして数える。QIDMと同じ)。履歴の番号を返す。
    """
    with _connect(db_path) as conn:
        _require_open(conn, draft_id)
        revisions = drama_version_store.list_revisions(conn, draft_id)
        undone = 0
        index = len(revisions) - 1
        while index > 0 and revisions[index].operation == "undo":
            undone += 1
            index -= 1
        index -= undone
        if index < 1:
            raise ValueError("取り消せる変更がありません")
        snapshot = drama_version_store.read_revision_snapshot(
            conn, draft_id, revisions[index - 1].revision
        )
        return drama_version_store.add_revision(conn, draft_id, "undo", snapshot)


def confirm_draft(db_path: str, draft_id: str, note: Optional[str] = None) -> int:
    """
    下書きを確定する: 正本を下書きの中身で書き直し、版を1つ足し、下書きをconfirmedにする(1つのトランザクション)。
    新しい版の番号を返す。下書きの元にした版が今の版と違えばDraftConflictError。
    """
    with _connect(db_path) as conn:
        draft = _require_open(conn, draft_id)
        current = drama_version_store.current_version(conn)
        if draft.base_version != current:
            raise DraftConflictError(
                f"下書き {draft_id} は版 {draft.base_version} を元にしていますが、今の版は {current} です"
                "(最新の版から下書きを作り直してください)"
            )
        snapshot = drama_version_store.read_revision_snapshot(conn, draft_id)
        drama_model_store.write_model(conn, build_model_definition_from_yaml(snapshot))
        version = drama_version_store.add_version(conn, snapshot, draft_id, note)
        drama_version_store.set_draft_status(conn, draft_id, "confirmed")
        return version


def discard_draft(db_path: str, draft_id: str) -> None:
    """下書きを破棄する(discarded。履歴は残す)。"""
    with _connect(db_path) as conn:
        _require_open(conn, draft_id)
        drama_version_store.set_draft_status(conn, draft_id, "discarded")
