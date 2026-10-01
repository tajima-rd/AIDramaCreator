# core/model/agent/actor.py
"""Actor。台詞を音声にする演者。"""

from typing import Optional

from core.model.agent.agent_task import AgentTask
from core.model.agent.base_agent import BaseAgent


class Actor(BaseAgent):
    """配役(Cast)ごとに1つ。割り当てられた人物の台詞(Dialogue)を、演出と配役の演じ方に従って音声にする。
    人物になりきって台詞を考える者ではない。casting_idは演じる配役(ID参照)、voice_nameは使う声の名前
    (音声合成の提供元・モデルは、現状はproject.yamlのgenai.tts。docs/model_design.md)。"""

    def __init__(
        self,
        casting_id: str,
        name: str,
        voice_name: Optional[str] = None,
        role: Optional[str] = None,
        persona: Optional[str] = None,
        rules: Optional[list[str]] = None,
        prohibitions: Optional[list[str]] = None,
        tasks: Optional[list[AgentTask]] = None,
    ):
        super().__init__(name, role, persona, rules, prohibitions, tasks)
        self.casting_id: str = casting_id
        self.voice_name: Optional[str] = voice_name

    @classmethod
    def default_role(cls) -> str:
        return "配役の人物の台詞を、演出と演じ方に従って音声にする。"

    @classmethod
    def default_rules(cls) -> list[str]:
        return [
            "台詞の文言どおりに読む。",
        ]

    @classmethod
    def default_prohibitions(cls) -> list[str]:
        return [
            "台詞に無い言葉を足さない。",
            "音声タグを読み上げない。",
        ]

    @classmethod
    def default_tasks(cls) -> list[AgentTask]:
        return [
            AgentTask(
                "perform_dialogue",
                "台詞を演じる",
                "台詞を、演出と配役の演じ方に従って音声にする。",
            ),
        ]
