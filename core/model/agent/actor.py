# core/model/agent/actor.py
"""Actor。台詞を音声にする演者。"""

from typing import Optional

from core.model.agent.agent import Agent


class Actor(Agent):
    """Castingごとに1つ。割り当てられた人物の台詞(Dialogue)を、演出に従って音声にする。
    人物になりきって台詞を考える者ではない。"""

    def __init__(
        self,
        casting_id: str,
        name: str,
        persona: Optional[str] = None,
    ):
        super().__init__(name, persona=persona)
        self.casting_id: str = casting_id
