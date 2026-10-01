# core/model/agent/stage_manager.py
"""StageManager。進行を管理する。"""

from core.model.agent.base_agent import BaseAgent


class StageManager(BaseAgent):
    """原稿を音声の生成に回し、必要なら翻訳する。音声の実際の長さと演出の間から、キューシート(CueSheet)を作る
    (キューシートの組み立てはプログラムで、タスクにしない)。"""
