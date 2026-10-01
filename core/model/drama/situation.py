# core/model/drama/situation.py
"""
場面の状況(2026-10-01ユーザー決定)。シーンが持ち、台詞(Dialogue)は場面の途中で変わるときだけ自分の状況で上書きする。
シーンの場所はScene.locationが持つので、シーンの状況のlocationは通常は空で、台詞で場所が変わるときに使う。
"""

from typing import Optional

from core.model.drama.location import Location


class Situation:
    """locationは場所(参照)、descriptionは状況(例: 雪景色を見ている)、time_of_dayは時間帯(例: 昼)、
    environmentは天候・環境(例: 雪・静かな室内)。シーン・台詞が値として所有する(識別子は持たない)。"""

    def __init__(
        self,
        location: Optional[Location] = None,
        description: Optional[str] = None,
        time_of_day: Optional[str] = None,
        environment: Optional[str] = None,
    ):
        self.location: Optional[Location] = location  # 参照
        self.description: Optional[str] = description
        self.time_of_day: Optional[str] = time_of_day
        self.environment: Optional[str] = environment
