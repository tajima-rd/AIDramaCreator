# core/model/agent/stage_manager.py
"""StageManager。進行を管理する。"""

from core.model.agent.agent import Agent


class StageManager(Agent):
    """ほかのエージェントへ発注し、音声の実際の長さと演出の間から、キューシート(CueSheet)を作る。"""
