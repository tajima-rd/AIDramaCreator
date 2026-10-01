# core/model/agent/sound_engineer.py
"""SoundEngineer。音響を担う。"""

from core.model.agent.base_agent import BaseAgent


class SoundEngineer(BaseAgent):
    """キューシート(CueSheet)に従って、シーンの音声を結合する(結合はプログラム)。将来は効果音・BGM・空間処理も担う。"""
