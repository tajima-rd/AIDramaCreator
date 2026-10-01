# core/model/agent/scriptwriter.py
"""Scriptwriter。企画書・人物・あらすじ・台詞を書く。"""

from core.model.agent.base_agent import BaseAgent


class Scriptwriter(BaseAgent):
    """企画書、人物(経歴・人物関係)、各階層のあらすじ、台詞(Script)を書く。"""
