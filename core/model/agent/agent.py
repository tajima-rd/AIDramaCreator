# core/model/agent/agent.py
"""
作品作りに参加するエージェントの基底。職能ごとにサブクラスがある(producer・researcher・casting_director・
scriptwriter・director・stage_manager・actor・sound_engineer)。

personaは、エージェントの性格づけ。
"""

from typing import Optional

from core.model.identifier import new_id


class Agent:
    """エージェントの基底。"""

    def __init__(self, name: str, persona: Optional[str] = None):
        self.id: str = new_id()  # 識別子(不変)。nameは変更できる名前
        self.name: str = name
        self.persona: Optional[str] = persona
