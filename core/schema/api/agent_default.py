# core/schema/api/agent_default.py
"""
エージェントのユーザー既定(core.service.api.agent_default)のDTO。エージェントの中身は、モデル定義YAMLの形(AgentSpec)で
やり取りする(作品のdramaturgy.agentsにそのまま重ねられる)。
"""

from pydantic import BaseModel

from core.schema.formats.dramaturgy_definition import AgentSpec


class AgentDefaultListResult(BaseModel):
    """職能の名前(モデル定義YAMLの区画名の単数形)→ユーザー既定。並びは職能の順。"""

    defaults: dict[str, AgentSpec]
