# core/model/agent/scriptwriter.py
"""Scriptwriter。企画書・人物・あらすじ・台詞を書く。"""

from core.model.agent.agent_task import AgentTask
from core.model.agent.base_agent import BaseAgent


class Scriptwriter(BaseAgent):
    """企画書、人物(経歴・人物関係)、各階層のあらすじ、台詞(Script)を書く。"""

    @classmethod
    def default_role(cls) -> str:
        return (
            "企画書・人物・あらすじ・台詞を書く。利用者と相談しながら、作品の設定を具体にしていく。"
        )

    @classmethod
    def default_rules(cls) -> list[str]:
        return [
            "与えられた企画書・人物の設定に沿って書く。",
            "台詞は、耳で聞いて分かる言葉で書く。",
        ]

    @classmethod
    def default_prohibitions(cls) -> list[str]:
        return [
            "与えられた設定を、断りなく変えない。",
            "擬音語など、音声の生成の障害になる表現を台詞に含めない。",
        ]

    @classmethod
    def default_tasks(cls) -> list[AgentTask]:
        return [
            AgentTask(
                "draft_proposal",
                "企画書を作る",
                "利用者と相談しながら、企画書(題・キャッチコピー・ログライン・企画意図・対象地域・あらすじ・登場人物)を作る。",
            ),
            AgentTask(
                "create_character",
                "人物を作る",
                "企画書とあらすじから、人物(人物像・経歴・人物関係)を作る。",
            ),
            AgentTask(
                "write_synopsis",
                "あらすじを書く",
                "作品・幕・シーンのあらすじを書く。",
            ),
            AgentTask(
                "write_dialogue",
                "台詞を書く",
                "シーンのあらすじと人物の設定から、台詞を書く。",
            ),
        ]
