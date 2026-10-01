# core/model/drama/script_element.py
"""
演出付きの原稿の段階(Directorが書く)。ScriptElementを基底に、台詞・効果音・環境音・BGMがある。
効果音・環境音・BGMは、当面は固有の属性を持たない。
"""

from typing import Optional

from core.model.drama.situation import Situation
from core.model.identifier import new_id


class Direction:
    """演出。抽象的な言葉で表す(間もミリ秒にしない)。"""

    def __init__(
        self,
        style: Optional[str] = None,
        pace: Optional[str] = None,
        dynamics: Optional[str] = None,
        emotion: Optional[str] = None,
        pause_after: Optional[str] = None,
    ):
        self.style: Optional[str] = style
        self.pace: Optional[str] = pace
        self.dynamics: Optional[str] = dynamics
        self.emotion: Optional[str] = emotion
        self.pause_after: Optional[str] = pause_after


class ScriptElement:
    """原稿の要素の基底。"""

    def __init__(self, order: int):
        self.id: str = new_id()  # 識別子(不変)
        self.order: int = order


class Dialogue(ScriptElement):
    """演出付きの台詞。line_idは元になったLine、cast_idは話者(Cast)で、どちらも識別子で参照する。textには音声タグを含められる。
    actionはト書き(動作・状況)。translated_textはDramaturgyのoutput_languageへの訳文。situationは、場面の途中で
    状況(場所・状況・時間帯・天候等)が変わるときだけ持つ(無ければシーンの状況)。"""

    def __init__(
        self,
        order: int,
        line_id: str,
        cast_id: str,
        text: str,
        action: Optional[str] = None,
        direction: Optional[Direction] = None,
        translated_text: Optional[str] = None,
        situation: Optional[Situation] = None,
    ):
        super().__init__(order)
        self.line_id: str = line_id
        self.cast_id: str = cast_id
        self.text: str = text
        self.action: Optional[str] = action
        self.direction: Direction = direction if direction is not None else Direction()
        self.translated_text: Optional[str] = translated_text
        self.situation: Optional[Situation] = situation


class SoundEffect(ScriptElement):
    """効果音(当面は固有の属性を持たない)。"""


class Atmosphere(ScriptElement):
    """環境音(当面は固有の属性を持たない)。"""


class Music(ScriptElement):
    """BGM(当面は固有の属性を持たない)。"""
