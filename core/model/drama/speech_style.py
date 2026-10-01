# core/model/drama/speech_style.py
"""
人物の話し方と語尾。どの作品の人物にもある要素なので、クラスとして持つ(2026-10-01ユーザー決定)。
相手によって変わる話し方(呼び方・口調)は人物関係(Relationship.form_of_address・tone)が、声で演じるときの
話す速さは配役の演じ方(Performance.pace)が持つ。
"""

from enum import StrEnum
from typing import Optional


class SentenceEndingKind(StrEnum):
    """語尾の種類。"""

    NORMAL = "normal"  # 通常
    CONJECTURE = "conjecture"  # 推測
    QUESTION = "question"  # 疑問
    NEGATION = "negation"  # 否定
    COMMAND = "command"  # 命令
    REQUEST = "request"  # 依頼
    EXCLAMATION = "exclamation"  # 感嘆


class SentenceEnding:
    """語尾。kindは種類、examplesは例(例: 〜している。)、descriptionは説明(使う場面等)。"""

    def __init__(
        self,
        kind: SentenceEndingKind,
        examples: Optional[list[str]] = None,
        description: Optional[str] = None,
    ):
        self.kind: SentenceEndingKind = kind
        self.examples: list[str] = list(examples or [])
        self.description: Optional[str] = description


class SpeechStyle:
    """話し方。first_personは一人称(自分の呼び方。例: オレ)、toneは相手を問わない既定の口調、endingsは語尾、
    descriptionはその他の説明。"""

    def __init__(
        self,
        first_person: Optional[str] = None,
        tone: Optional[str] = None,
        endings: Optional[list[SentenceEnding]] = None,
        description: Optional[str] = None,
    ):
        self.first_person: Optional[str] = first_person
        self.tone: Optional[str] = tone
        self.endings: list[SentenceEnding] = list(endings or [])
        self.description: Optional[str] = description
