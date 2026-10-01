# core/model/agent/sound_engineer.py
"""SoundEngineer。音声を結合する。"""

from core.model.agent.agent import Agent


class SoundEngineer(Agent):
    """キューシート(CueSheet)に従って、シーンの音声を結合する。将来は効果音・BGM・空間処理も担う。"""
