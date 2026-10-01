# core/model/agent/researcher.py
"""Researcher。前提の知識と物語に関わる知識の資料を扱う。"""

from core.model.agent.base_agent import BaseAgent


class Researcher(BaseAgent):
    """資料をもとに、ほかのエージェントの問いに根拠を出典付きで返す。考証も行う。作品は書き換えない。"""
