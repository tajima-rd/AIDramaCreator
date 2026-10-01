# core/model/agent/director.py
"""Director。台詞に演出を付ける。"""

from core.model.agent.agent_task import AgentTask
from core.model.agent.base_agent import BaseAgent


class Director(BaseAgent):
    """台詞(Script)に演出を付けて、演出付きの原稿(ScriptElement)にする。"""

    @classmethod
    def default_role(cls) -> str:
        return "台詞に演出を付けて、演出付きの原稿にする。"

    @classmethod
    def default_rules(cls) -> list[str]:
        return [
            "演出は抽象的な言葉で表す(間の長さ等をミリ秒にしない)。",
        ]

    @classmethod
    def default_prohibitions(cls) -> list[str]:
        return [
            "台詞の文言を変えない。",
        ]

    @classmethod
    def default_tasks(cls) -> list[AgentTask]:
        return [
            AgentTask(
                "direct_scene",
                "原稿を作る",
                "シーンの台詞に、ト書きと演出(話し方・速さ・強弱・感情・後の間)を付ける。",
            ),
        ]
