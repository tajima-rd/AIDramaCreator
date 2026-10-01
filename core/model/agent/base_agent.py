# core/model/agent/base_agent.py
"""
作品作りに参加するエージェントの基底(抽象クラス)。エージェントは生成AIが担う職能で、職能ごとにサブクラスがある
(researcher・casting_director・scriptwriter・director・stage_manager・sound_engineer・actor)。Producerは利用者本人なので
モデルに置かない(2026-10-01ユーザー決定)。

生成AIへのプロンプトを組み立てるための情報を属性として持つ(プロンプトの文そのものは持たない。組み立てはcore.prompt):
role(役割の説明)・persona(性格づけ)・rules(どのタスクでも守ること)・prohibitions(どのタスクでもしてはいけないこと)・
tasks(担う仕事。AgentTask)。作品ごとに書き換えた後の全文を持つ。

職能ごとの既定の文面とタスクの一覧の正本は、core/default/agents/のYAML(システム既定。2026-10-02ユーザー決定)。
モデルはファイルを読まないので、既定での補完とタスクのcodeの検査は、読み込みの側(core.infra.io.agent_default_reader)が行う。
"""

from abc import ABC
from typing import Optional

from core.model.agent.agent_task import AgentTask
from core.model.identifier import new_id


# 抽象メソッドは無い(既定の文面はYAMLに移した)が、職能を表さないので直接は使わない
class BaseAgent(ABC):  # noqa: B024
    """職能ごとのサブクラスで使う(このクラスそのものは職能を表さない)。"""

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
        self.role: Optional[str] = role
        self.persona: Optional[str] = persona
        self.rules: list[str] = list(rules or [])
        self.prohibitions: list[str] = list(prohibitions or [])
        self.tasks: list[AgentTask] = list(tasks or [])
