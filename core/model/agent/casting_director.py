# core/model/agent/casting_director.py
"""CastingDirector。配役と演じ方を決める。"""

from core.model.agent.agent_task import AgentTask
from core.model.agent.base_agent import BaseAgent


class CastingDirector(BaseAgent):
    """人物(Character)の配役(Cast)と、その役の演じ方(Performance)を決め、どの演者(Actor)に任せるかを決める。"""

    @classmethod
    def default_role(cls) -> str:
        return "人物に配役し、その役の演じ方を決め、どの声で演じるかを選ぶ。"

    @classmethod
    def default_rules(cls) -> list[str]:
        return [
            "人物の年齢・性別・人物像に合う声を選ぶ。",
        ]

    @classmethod
    def default_prohibitions(cls) -> list[str]:
        return [
            "人物の設定を書き換えない。",
        ]

    @classmethod
    def default_tasks(cls) -> list[AgentTask]:
        return [
            AgentTask(
                "cast_character",
                "配役と演じ方を決める",
                "人物ごとに配役を作り、演じ方(役の説明・話す速さ)と声の性別を決める。",
            ),
            AgentTask(
                "assign_voice",
                "声を選ぶ",
                "配役ごとに、音声合成の声の一覧から演じる声を選ぶ。",
            ),
        ]
