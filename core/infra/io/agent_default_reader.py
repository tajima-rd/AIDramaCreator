# core/infra/io/agent_default_reader.py
"""
エージェントのシステム既定(core/default/agents/<職能>.yaml。2026-10-02ユーザー決定)の読み込みと、既定による補完。

システム既定は、職能ごとの既定の文面(役割・厳守事項・禁止事項)と、タスク(code)の一覧の正本。ファイルは作品の分割ファイルと
同じ形(dramaturgy.agents.<職能の複数形>に1人)。プロジェクトのユーザー既定(core.infra.store.agent_default_store)も同じ形。

- complete_agent_spec: モデル定義YAML・ユーザー既定で省略した項目(role・rules・prohibitions、タスクとタスクの中の項目)を
  システム既定で補い、タスクをシステム既定の並びにそろえる。システム既定に無いcodeと、重複したcodeはValueError。
"""

import functools
from pathlib import Path

import yaml

from core.model.agent.factory import AGENT_ROLES
from core.schema.formats.dramaturgy_definition import AgentSpec, AgentTaskSpec

SYSTEM_DEFAULT_DIR = Path(__file__).resolve().parents[2] / "default" / "agents"
# システム既定のある職能(モデル定義YAMLの区画名の単数形)。Actorは配役ごとに置くので、ユーザー既定には含めない
SYSTEM_DEFAULT_ROLES: tuple[str, ...] = (*AGENT_ROLES, "actor")
USER_DEFAULT_ROLES: tuple[str, ...] = tuple(AGENT_ROLES)


def parse_agent_default(text: str, role_name: str) -> AgentSpec:
    """既定のYAMLの文字列から、その職能のエージェント(1人)を取り出す。形が違えばValueError。"""
    document = yaml.safe_load(text) or {}
    agents = (
        (document.get("dramaturgy") or {}).get("agents") if isinstance(document, dict) else None
    )
    section = f"{role_name}s"
    if not isinstance(agents, dict) or set(agents) != {section}:
        raise ValueError(f"既定のYAMLには、dramaturgy.agents.{section}だけを書いてください")
    items = agents[section]
    if not isinstance(items, list) or len(items) != 1:
        raise ValueError(
            f"既定のYAMLのdramaturgy.agents.{section}には、エージェントを1人だけ書いてください"
        )
    values = {k: v for k, v in items[0].items() if k not in ("cast", "voice_name")}
    return AgentSpec.model_validate(values)


@functools.cache
def _system_default(role_name: str) -> AgentSpec:
    if role_name not in SYSTEM_DEFAULT_ROLES:
        raise ValueError(f"エージェントの職能 '{role_name}' はありません")
    path = SYSTEM_DEFAULT_DIR / f"{role_name}.yaml"
    return parse_agent_default(path.read_text(encoding="utf-8"), role_name)


def system_default(role_name: str) -> AgentSpec:
    """職能のシステム既定(呼ぶたびに複製を返す)。"""
    return _system_default(role_name).model_copy(deep=True)


def system_default_text(role_name: str) -> str:
    """職能のシステム既定のファイルの文字列(ユーザー既定へ複製するときに使う)。"""
    system_default(role_name)  # 職能の確認
    return (SYSTEM_DEFAULT_DIR / f"{role_name}.yaml").read_text(encoding="utf-8")


def complete_agent_spec[SpecT: AgentSpec](role_name: str, spec: SpecT) -> SpecT:
    """省略した項目をシステム既定で補い、タスクをシステム既定の並びにそろえたエージェント(元のspecは変えない)。"""
    default = _system_default(role_name)
    given: dict[str, AgentTaskSpec] = {}
    for task in spec.tasks:
        if task.code in given:
            raise ValueError(f"エージェント '{spec.name}' のタスク '{task.code}' が重複しています")
        given[task.code] = task
    known = {task.code for task in default.tasks}
    unknown = [code for code in given if code not in known]
    if unknown:
        raise ValueError(
            f"エージェント '{spec.name}': 職能 '{role_name}' にタスク '{unknown[0]}' はありません"
        )
    tasks = []
    for base in default.tasks:
        task = given.get(base.code)
        tasks.append(
            AgentTaskSpec(
                code=base.code,
                title=task.title if task and task.title is not None else base.title,
                description=(
                    task.description if task and task.description is not None else base.description
                ),
                rules=list(task.rules if task and task.rules is not None else base.rules or []),
                prohibitions=list(
                    task.prohibitions
                    if task and task.prohibitions is not None
                    else base.prohibitions or []
                ),
            )
        )
    return spec.model_copy(
        update={
            "role": spec.role if spec.role is not None else default.role,
            "rules": list(spec.rules if spec.rules is not None else default.rules or []),
            "prohibitions": list(
                spec.prohibitions if spec.prohibitions is not None else default.prohibitions or []
            ),
            "tasks": tasks,
        }
    )
