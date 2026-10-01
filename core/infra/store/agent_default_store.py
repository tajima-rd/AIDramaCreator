# core/infra/store/agent_default_store.py
"""
プロジェクトのエージェントのユーザー既定(<プロジェクト>/user_default/agents/<職能>.yaml。2026-10-02ユーザー決定)の読み書き。

ユーザー既定は、そのプロジェクトで新しく作る作品と、エージェントを既定に戻す(Reset to Default)ときに使う。
プロジェクトの作成時にシステム既定(core/default/agents/)を複製して作り、無い職能は使うときに複製する(このフォルダが無い
既存のプロジェクトのため)。形はシステム既定と同じ(core.infra.io.agent_default_reader)。書き換えられるのは文面だけで、
タスクの一覧(code)はシステム既定に従う。Actorは配役ごとに置くので、ユーザー既定は持たない。
"""

import os

from core.infra.io.agent_default_reader import (
    USER_DEFAULT_ROLES,
    complete_agent_spec,
    parse_agent_default,
    system_default_text,
)
from core.infra.io.model_definition_writer import dump_model_definition
from core.project.project import ProjectLayout
from core.schema.formats.dramaturgy_definition import AgentSpec

_HEADER = (
    "# {role_name}のユーザー既定(このプロジェクトで新しく作る作品と、既定に戻すときに使う)。\n"
    "# AIDC ConsoleのAgentsタブ(Save as User Default)で書き換えられる。形はシステム既定(core/default/agents/)と同じ。\n"
)


def _path(layout: ProjectLayout, role_name: str) -> str:
    if role_name not in USER_DEFAULT_ROLES:
        raise ValueError(f"ユーザー既定のある職能ではありません: '{role_name}'")
    return os.path.join(layout.user_default_agents_dir, f"{role_name}.yaml")


def ensure_user_defaults(layout: ProjectLayout) -> None:
    """無い職能のユーザー既定を、システム既定から複製する(あるものは変えない)。"""
    os.makedirs(layout.user_default_agents_dir, exist_ok=True)
    for role_name in USER_DEFAULT_ROLES:
        path = _path(layout, role_name)
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                f.write(system_default_text(role_name))


def read_user_default(layout: ProjectLayout, role_name: str) -> AgentSpec:
    """職能のユーザー既定(省略した項目はシステム既定で補ったもの)。"""
    path = _path(layout, role_name)
    if not os.path.exists(path):
        ensure_user_defaults(layout)
    with open(path, encoding="utf-8") as f:
        text = f.read()
    return complete_agent_spec(role_name, parse_agent_default(text, role_name))


def read_user_defaults(layout: ProjectLayout) -> dict[str, AgentSpec]:
    """すべての職能のユーザー既定(職能の名前→エージェント。並びは職能の順)。"""
    ensure_user_defaults(layout)
    return {role_name: read_user_default(layout, role_name) for role_name in USER_DEFAULT_ROLES}


def write_user_default(layout: ProjectLayout, role_name: str, spec: AgentSpec) -> AgentSpec:
    """職能のユーザー既定を書く(識別子は書かない。省略した項目はシステム既定で補ってから全文を書く)。"""
    path = _path(layout, role_name)
    full = complete_agent_spec(role_name, spec)
    values = full.model_dump(exclude={"id", "key"}, exclude_none=True)
    os.makedirs(layout.user_default_agents_dir, exist_ok=True)
    text = _HEADER.format(role_name=role_name) + dump_model_definition(
        {"dramaturgy": {"agents": {f"{role_name}s": [values]}}}
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return read_user_default(layout, role_name)


def restore_system_default(layout: ProjectLayout, role_name: str) -> AgentSpec:
    """職能のユーザー既定を、システム既定で書き直す。"""
    path = _path(layout, role_name)
    os.makedirs(layout.user_default_agents_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(system_default_text(role_name))
    return read_user_default(layout, role_name)
