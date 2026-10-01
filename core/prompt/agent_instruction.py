# core/prompt/agent_instruction.py
"""
エージェント(core.model.agent)の情報から、生成AIへの指示(システムの指示)の節を組み立てる共通の部品。
エージェントが持つのは、役割・性格づけ・どのタスクでも守ること・してはいけないことと、タスクごとの文面(docs/model_design.md)。
用途ごとのプロンプト(何を返させるか)は、各用途のモジュールが、この節の後に足す。
"""

from typing import Optional

from core.genai.prompt import BulletInstruction, ForbiddenRule, MandatoryRule, PromptComponent, Section, TextBlock
from core.model.agent.agent_task import AgentTask
from core.model.agent.base_agent import BaseAgent


def find_task(agent: BaseAgent, task_code: str) -> Optional[AgentTask]:
    return next((task for task in agent.tasks if task.code == task_code), None)


def agent_task_sections(agent: Optional[BaseAgent], task_code: str) -> list[PromptComponent]:
    """エージェントと、そのタスク(task_code)の文面の節。agentがNoneなら空(用途ごとの指示だけで動かす)。"""
    if agent is None:
        return []
    role_children: list[PromptComponent] = [TextBlock(f"あなたは{agent.name}です。{agent.role or ''}")]
    if agent.persona:
        role_children.append(TextBlock(agent.persona))
    sections: list[PromptComponent] = [Section(title="役割", children=role_children)]

    task = find_task(agent, task_code)
    rules = list(agent.rules) + (list(task.rules) if task else [])
    prohibitions = list(agent.prohibitions) + (list(task.prohibitions) if task else [])
    task_children: list[PromptComponent] = []
    if task and (task.title or task.description):
        task_children.append(TextBlock(": ".join(text for text in (task.title, task.description) if text)))
    if rules:
        task_children.append(MandatoryRule(BulletInstruction(items=rules)))
    if prohibitions:
        task_children.append(ForbiddenRule(BulletInstruction(items=prohibitions)))
    if task_children:
        sections.append(Section(title="タスク", children=task_children))
    return sections
