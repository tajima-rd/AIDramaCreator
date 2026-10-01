# core/service/api/agent_default.py
"""
エージェントのユーザー既定の公開API(プロジェクトごと。docs/model_design.md「core/model/agent/」)。

エラーは例外で返す: project_idが未登録ならProjectNotFoundError、ユーザー既定の無い職能・システム既定に無いタスクのcodeは
ValueError。
"""

from core.infra.store import agent_default_store
from core.infra.store.project_registry_store import resolve_layout
from core.schema import AgentDefaultListResult
from core.schema.formats.dramaturgy_definition import AgentSpec


def list_agent_defaults(project_id: str) -> AgentDefaultListResult:
    """すべての職能のユーザー既定(無ければシステム既定から作る)。"""
    return AgentDefaultListResult(
        defaults=agent_default_store.read_user_defaults(resolve_layout(project_id))
    )


def save_agent_default(project_id: str, role_name: str, spec: AgentSpec) -> AgentSpec:
    """職能のユーザー既定を保存する(Save as User Default)。省略した項目はシステム既定で補う。"""
    return agent_default_store.write_user_default(resolve_layout(project_id), role_name, spec)


def restore_system_default(project_id: str, role_name: str) -> AgentSpec:
    """職能のユーザー既定を、システム既定に戻す(Restore System Default)。作品の中身は変えない。"""
    return agent_default_store.restore_system_default(resolve_layout(project_id), role_name)
