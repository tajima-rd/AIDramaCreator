# core/model/agent/director.py
"""Director。台詞に演出を付ける。"""

from core.model.agent.base_agent import BaseAgent


class Director(BaseAgent):
    """台詞(Script)に演出を付けて、演出付きの原稿(ScriptElement)にする。"""
