# core/model/agent/director.py
"""Director。台詞に演出を付ける。"""

from core.model.agent.agent import Agent


class Director(Agent):
    """台詞(Script)に演出を付けて、演出付きの原稿(ScriptElement)にする。演出は抽象的な言葉で表し、ミリ秒にしない。"""
