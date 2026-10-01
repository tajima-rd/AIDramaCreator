# core/model/agent/actor.py
"""Actor。台詞を音声にする演者。"""

from typing import Optional

from core.model.agent.agent import Agent


class Actor(Agent):
    """配役(Cast)ごとに1つ。割り当てられた人物の台詞(Dialogue)を、演出と配役の演じ方に従って音声にする。
    人物になりきって台詞を考える者ではない。casting_idは演じる配役(ID参照)、voice_nameは使う声の名前
    (音声合成の提供元・モデルは、現状はproject.yamlのgenai.tts。docs/model_design.md)。"""

    def __init__(
        self,
        casting_id: str,
        name: str,
        voice_name: Optional[str] = None,
        persona: Optional[str] = None,
    ):
        super().__init__(name, persona=persona)
        self.casting_id: str = casting_id
        self.voice_name: Optional[str] = voice_name
