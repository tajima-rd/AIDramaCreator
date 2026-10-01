# core/model/agent/casting_director.py
"""CastingDirector。人物と声を対応付ける。"""

from typing import Optional

from core.model.agent.agent import Agent


class CastingDirector(Agent):
    """人物(Character)に声を割り当てる(Casting)。providerは声を選ぶ音声合成の提供元。
    提供元ごとの声の一覧の知識は、このエージェントに閉じ込める。"""

    def __init__(
        self,
        name: str,
        provider: Optional[str] = None,
        persona: Optional[str] = None,
    ):
        super().__init__(name, persona=persona)
        self.provider: Optional[str] = provider
