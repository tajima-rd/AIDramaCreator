# core/model/agent/stage_manager.py
"""StageManager。進行を管理する。"""

from core.model.agent.agent_task import AgentTask
from core.model.agent.base_agent import BaseAgent


class StageManager(BaseAgent):
    """原稿を音声の生成に回し、必要なら翻訳する。音声の実際の長さと演出の間から、キューシート(CueSheet)を作る(キューシートの組み立てはプログラムで、タスクにしない)。"""

    @classmethod
    def default_role(cls) -> str:
        return "制作の進行を管理する。原稿を音声の生成に回し、作品の出力の言語が違えば翻訳する。"

    @classmethod
    def default_tasks(cls) -> list[AgentTask]:
        return [
            AgentTask(
                "translate",
                "翻訳する",
                "原稿の台詞を、作品の入力の言語から出力の言語へ訳す。",
                rules=[
                    "話者・演出・意味を保って訳す。",
                ],
            ),
        ]
