# core/model/agent/__init__.py
"""
作品作りに参加するエージェントのモデル(docs/model_design.md)。クラスと属性だけを定義している(機能は合意してから加える)。
"""

from core.model.agent.actor import Actor
from core.model.agent.agent import Agent
from core.model.agent.casting_director import CastingDirector
from core.model.agent.director import Director
from core.model.agent.producer import Producer
from core.model.agent.researcher import Researcher
from core.model.agent.scriptwriter import Scriptwriter
from core.model.agent.sound_engineer import SoundEngineer
from core.model.agent.stage_manager import StageManager

__all__ = [
    "Actor",
    "Agent",
    "CastingDirector",
    "Director",
    "Producer",
    "Researcher",
    "Scriptwriter",
    "SoundEngineer",
    "StageManager",
]
