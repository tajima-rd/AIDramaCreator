# core/model/agent/sound_engineer.py
"""SoundEngineer。音響を担う。"""

from core.model.agent.agent_task import AgentTask
from core.model.agent.base_agent import BaseAgent


class SoundEngineer(BaseAgent):
    """キューシート(CueSheet)に従って、シーンの音声を結合する(結合はプログラム)。将来は効果音・BGM・空間処理も担う。"""

    @classmethod
    def default_role(cls) -> str:
        return "シーンの音響を担う。効果音・環境音・BGMを決める。"

    @classmethod
    def default_tasks(cls) -> list[AgentTask]:
        return [
            AgentTask(
                "design_sound",
                "音響を設計する",
                "シーンの状況から、効果音・環境音・BGMを決める。",
            ),
        ]
