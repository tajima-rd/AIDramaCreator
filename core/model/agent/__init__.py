"""
作品作りに参加するエージェント(生成AIが担う職能)のモデル(docs/model_design.md)。クラスと属性だけを定義している
(生成AIの呼び出しは処理の側)。各職能の既定の役割・厳守事項・禁止事項・タスクは暫定の文面(2026-10-01)。
"""

from core.model.agent.actor import Actor
from core.model.agent.agent_task import AgentTask
from core.model.agent.base_agent import BaseAgent
from core.model.agent.casting_director import CastingDirector
from core.model.agent.director import Director
from core.model.agent.researcher import Researcher
from core.model.agent.scriptwriter import Scriptwriter
from core.model.agent.sound_engineer import SoundEngineer
from core.model.agent.stage_manager import StageManager

__all__ = [
    "Actor",
    "AgentTask",
    "BaseAgent",
    "CastingDirector",
    "Director",
    "Researcher",
    "Scriptwriter",
    "SoundEngineer",
    "StageManager",
]
