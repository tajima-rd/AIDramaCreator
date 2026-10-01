# core/model/agent/factory.py
"""
値からエージェントを組み立てる関数(docs/model_design.md「モデルの組み立てと生成AIとの受け渡し」)。
DB・ファイルには触れず、組み立てたオブジェクトを返すだけ。キーワード引数idで既存の識別子を保てる(QIDMの_keeps_id)。
"""

import functools
from typing import Optional

from core.model.agent.actor import Actor
from core.model.agent.agent_task import AgentTask
from core.model.agent.base_agent import BaseAgent
from core.model.agent.casting_director import CastingDirector
from core.model.agent.director import Director
from core.model.agent.researcher import Researcher
from core.model.agent.scriptwriter import Scriptwriter
from core.model.agent.sound_engineer import SoundEngineer
from core.model.agent.stage_manager import StageManager

# 固有の属性を持たないエージェント。職能の名前(モデル定義YAMLの区画名の単数形)→クラス。並びが書き出す順
AGENT_ROLES: dict[str, type[BaseAgent]] = {
    "researcher": Researcher,
    "casting_director": CastingDirector,
    "scriptwriter": Scriptwriter,
    "director": Director,
    "stage_manager": StageManager,
    "sound_engineer": SoundEngineer,
}


def _keeps_id(builder):
    """build_*に、キーワード引数id(既存のエンティティの識別子)を足す。省略すれば新しいidのまま。"""

    @functools.wraps(builder)
    def wrapper(*args, id: Optional[str] = None, **kwargs):
        entity = builder(*args, **kwargs)
        if id is not None:
            entity.id = id
        return entity

    return wrapper


@_keeps_id
def build_agent(
    role_name: str,
    name: str,
    role: Optional[str] = None,
    persona: Optional[str] = None,
    rules: Optional[list[str]] = None,
    prohibitions: Optional[list[str]] = None,
    tasks: Optional[list[AgentTask]] = None,
) -> BaseAgent:
    """固有の属性を持たないエージェント(AGENT_ROLES)。role_nameは職能の名前、roleは役割の説明(Noneなら既定)。"""
    if role_name not in AGENT_ROLES:
        raise ValueError(f"エージェントの職能 '{role_name}' はありません")
    return AGENT_ROLES[role_name](name, role, persona, rules, prohibitions, tasks)


@_keeps_id
def build_actor(
    casting_id: str,
    name: str,
    voice_name: Optional[str] = None,
    role: Optional[str] = None,
    persona: Optional[str] = None,
    rules: Optional[list[str]] = None,
    prohibitions: Optional[list[str]] = None,
    tasks: Optional[list[AgentTask]] = None,
) -> Actor:
    return Actor(casting_id, name, voice_name, role, persona, rules, prohibitions, tasks)
