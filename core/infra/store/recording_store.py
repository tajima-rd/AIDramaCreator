# core/infra/store/recording_store.py
"""
生成した音声(Dramaturgy EditorのRecordingタブ)のファイル。<プロジェクト>/recordings/<作品のid>/<言語>/<シーンのid>.mp3。

シーンごとに1つの音声で、生成し直すと上書きする。作品の版(Save Version)とは結び付けない。題・並びは変わりうるので、
作品とシーンは識別子で持つ(幕・シーンの番号と題は、画面に出すときに今の作品から引く)。
"""

import os
import re
from datetime import UTC, datetime
from typing import Optional

from core.project.project import ProjectLayout

EXTENSION = ".mp3"
MEDIA_TYPE = "audio/mpeg"

_SAFE = re.compile(r"^[A-Za-z0-9_-]+$")


class RecordingFile:
    """生成した音声のファイル。recorded_atは書き出した日時(ISO 8601)。"""

    def __init__(self, path: str, size: int, recorded_at: str):
        self.path: str = path
        self.size: int = size
        self.recorded_at: str = recorded_at


def _part(value: str, label: str) -> str:
    """パスの1要素(識別子・言語のコード)。パスを辿れる文字は断る。"""
    if not value or not _SAFE.match(value):
        raise ValueError(f"{label}「{value}」はパスに使えません。")
    return value


def recording_path(layout: ProjectLayout, dramaturgy_id: str, language: str, scene_id: str) -> str:
    return os.path.join(
        layout.recordings_dir,
        _part(dramaturgy_id, "作品のid"),
        _part(language, "言語"),
        _part(scene_id, "シーンのid") + EXTENSION,
    )


def save_recording(layout: ProjectLayout, dramaturgy_id: str, language: str, scene_id: str, data: bytes) -> RecordingFile:
    """音声を書き出す(あれば上書き)。書きかけのファイルを残さないよう、一時ファイルに書いてから置き換える。"""
    path = recording_path(layout, dramaturgy_id, language, scene_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp = path + ".part"
    with open(temp, "wb") as f:
        f.write(data)
    os.replace(temp, path)
    return find_recording(layout, dramaturgy_id, language, scene_id)


def find_recording(layout: ProjectLayout, dramaturgy_id: str, language: str, scene_id: str) -> Optional[RecordingFile]:
    """シーンの音声(無ければNone)。"""
    path = recording_path(layout, dramaturgy_id, language, scene_id)
    if not os.path.isfile(path):
        return None
    stat = os.stat(path)
    recorded_at = datetime.fromtimestamp(stat.st_mtime, UTC).astimezone().isoformat()
    return RecordingFile(path, stat.st_size, recorded_at)
