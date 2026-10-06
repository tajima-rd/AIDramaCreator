# core/schema/api/recording.py
"""
音声の生成(core.service.api.recording。Dramaturgy EditorのRecordingタブ)のDTO。音声はシーンごとに1つのmp3で、
<プロジェクト>/recordings/<作品のid>/<言語>/<シーンのid>.mp3に置く。読み込む作品は編集用の下書き(draft_id)のもの。
"""

from typing import Literal, Optional

from pydantic import BaseModel


class RecordingLanguageInfo(BaseModel):
    code: str  # 言語のコード(例: ja)
    source: Literal["text", "translation"]  # 読み上げる原稿の項目(音声にする文・その言語の訳文)


class RecordingSceneInfo(BaseModel):
    scene_id: str
    act_number: int  # 幕の番号(1から)
    scene_number: int  # 幕の中のシーンの番号(1から)
    title: Optional[str] = None
    line_count: int  # 台詞の数
    problems: list[str] = []  # 音声を作るのに足りないもの(空なら作れる)
    notices: list[str] = []  # 作れるが確かめるとよいこと(読む言語の声が無く、既定の声で読む演者)
    recorded: bool  # 音声があるか
    recorded_at: Optional[str] = None
    size: Optional[int] = None  # 音声のファイルの大きさ(バイト)


class RecordingListResult(BaseModel):
    languages: list[RecordingLanguageInfo]  # 作品で作れる言語
    language: Optional[str] = None  # 一覧の言語(作れる言語が無ければNone)
    scenes: list[RecordingSceneInfo]


class RecordingCreateRequest(BaseModel):
    draft_id: str  # 原稿を読む編集用の下書き
    dramaturgy_id: str
    scene_id: str
    language: str
