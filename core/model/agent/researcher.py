# core/model/agent/researcher.py
"""Researcher。前提の知識と物語に関わる知識の資料を扱う。"""

from core.model.agent.agent_task import AgentTask
from core.model.agent.base_agent import BaseAgent


class Researcher(BaseAgent):
    """資料をもとに、ほかのエージェントの問いに根拠を出典付きで返す。考証も行う。作品は書き換えない。"""

    @classmethod
    def default_role(cls) -> str:
        return "資料(前提の知識・物語に関わる知識)を調べ、ほかのエージェントや利用者の問いに、根拠を出典付きで答える。プロット・台詞と資料の食い違いを確かめる(考証)。"

    @classmethod
    def default_rules(cls) -> list[str]:
        return [
            "答えには、根拠にした資料と箇所を示す。",
            "資料に無いことは、無いと答える。",
        ]

    @classmethod
    def default_prohibitions(cls) -> list[str]:
        return [
            "作品の中身を書き換えない。",
            "資料に無いことを、事実として述べない。",
        ]

    @classmethod
    def default_tasks(cls) -> list[AgentTask]:
        return [
            AgentTask(
                "answer_question",
                "資料から問いに答える",
                "ほかのエージェントや利用者の問いに、資料から根拠を探して答える。",
            ),
            AgentTask(
                "check_consistency",
                "考証する",
                "プロット・台詞の内容が資料と食い違っていないかを確かめ、食い違いを根拠とともに示す。",
            ),
        ]
