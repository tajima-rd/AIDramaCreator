# core/model/agent/base_agent.py
"""
作品作りに参加するエージェントの基底(抽象クラス)。エージェントは生成AIが担う職能で、職能ごとにサブクラスがある
(researcher・casting_director・scriptwriter・director・stage_manager・sound_engineer・actor)。Producerは利用者本人なので
モデルに置かない(2026-10-01ユーザー決定)。

生成AIへのプロンプトを組み立てるための情報を属性として持つ(プロンプトの文そのものは持たない。組み立てはcore.prompt):
role(役割の説明)・persona(性格づけ)・rules(どのタスクでも守ること)・prohibitions(どのタスクでもしてはいけないこと)・
tasks(担う仕事。AgentTask)。既定の値は職能ごとのサブクラスがdefault_*で決め、作品ごとに書き換えられる
(書き換えた後の全文を持つ)。タスクの一覧は職能ごとに決まっていて(codeで特定)、書き換えられるのは文面だけ。
"""

from abc import ABC, abstractmethod
from typing import Optional

from core.model.agent.agent_task import AgentTask
from core.model.identifier import new_id


class BaseAgent(ABC):
    """role・rules・prohibitionsは、省略(None)すれば職能の既定の値。tasksは書き換えたタスク(codeで特定)だけを渡せばよく、
    渡さなかったタスクは既定の値になる。職能に無いcodeのタスクはValueError。"""

    def __init__(
        self,
        name: str,
        role: Optional[str] = None,
        persona: Optional[str] = None,
        rules: Optional[list[str]] = None,
        prohibitions: Optional[list[str]] = None,
        tasks: Optional[list[AgentTask]] = None,
    ):
        self.id: str = new_id()  # 識別子(不変)。nameは変更できる名前
        self.name: str = name
        self.role: str = role if role is not None else self.default_role()
        self.persona: Optional[str] = persona
        self.rules: list[str] = list(rules) if rules is not None else self.default_rules()
        self.prohibitions: list[str] = (
            list(prohibitions) if prohibitions is not None else self.default_prohibitions()
        )
        self.tasks: list[AgentTask] = self._with_default_tasks(tasks or [])

    @classmethod
    @abstractmethod
    def default_role(cls) -> str:
        """役割の説明の既定。"""

    @classmethod
    def default_rules(cls) -> list[str]:
        """どのタスクでも守ることの既定。"""
        return []

    @classmethod
    def default_prohibitions(cls) -> list[str]:
        """どのタスクでもしてはいけないことの既定。"""
        return []

    @classmethod
    @abstractmethod
    def default_tasks(cls) -> list[AgentTask]:
        """職能が担うタスク(既定の文面)。並びが表示の順。"""

    @classmethod
    def default_task(cls, code: str) -> AgentTask:
        """codeのタスクの既定。職能に無いcodeならValueError。"""
        for task in cls.default_tasks():
            if task.code == code:
                return task
        raise ValueError(f"{cls.__name__}にタスク '{code}' はありません")

    def _with_default_tasks(self, tasks: list[AgentTask]) -> list[AgentTask]:
        given: dict[str, AgentTask] = {}
        for task in tasks:
            self.default_task(task.code)  # 職能に無いcodeを断る
            if task.code in given:
                raise ValueError(f"{type(self).__name__}のタスク '{task.code}' が重複しています")
            given[task.code] = task
        return [given.get(default.code, default) for default in self.default_tasks()]
