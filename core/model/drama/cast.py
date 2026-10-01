# core/model/drama/cast.py
"""
配役。人物(Character)に声を割り当てたもので、台詞の話者になる。
"""

from typing import Optional

from core.model.drama.character import Character
from core.model.identifier import new_id


class Cast:
    """characterは演じる人物。providerは音声合成の提供元、voice_nameはその提供元での声の名前。
    notesは声の既定の話し方。"""

    def __init__(
        self,
        character: Character,
        provider: Optional[str] = None,
        voice_name: Optional[str] = None,
        language: Optional[str] = None,
        accent: Optional[str] = None,
        notes: Optional[str] = None,
    ):
        self.id: str = new_id()  # 識別子(不変)
        self.character: Character = character
        self.provider: Optional[str] = provider
        self.voice_name: Optional[str] = voice_name
        self.language: Optional[str] = language
        self.accent: Optional[str] = accent
        self.notes: Optional[str] = notes
