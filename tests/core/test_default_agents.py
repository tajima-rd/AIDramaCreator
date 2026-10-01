# tests/core/test_default_agents.py
"""
GUIの既定のエージェント(apps/AIDC-Console/default/agents/。職能ごとに1ファイル)が、作品に重ねて読めることと、
職能のクラスの既定の文面(core.model.agent)と食い違っていないこと。
"""

from pathlib import Path

import pytest

from core.infra.io.model_definition_reader import build_model_definition_from_yaml
from core.model.agent.factory import AGENT_ROLES

DEFAULT_AGENTS_DIR = (
    Path(__file__).resolve().parents[2] / "apps" / "AIDC-Console" / "default" / "agents"
)


def test_every_role_has_a_default_file():
    assert sorted(p.stem for p in DEFAULT_AGENTS_DIR.glob("*.yaml")) == sorted(AGENT_ROLES)


@pytest.mark.parametrize("role_name", sorted(AGENT_ROLES))
def test_default_file_matches_role_defaults(role_name):
    text = (DEFAULT_AGENTS_DIR / f"{role_name}.yaml").read_text(encoding="utf-8")
    (agent,) = build_model_definition_from_yaml(
        "dramaturgy: {title: 既定の確認}\n", text
    ).dramaturgy.agents
    cls = AGENT_ROLES[role_name]
    assert type(agent) is cls
    assert agent.role == cls.default_role()
    assert agent.rules == cls.default_rules()
    assert agent.prohibitions == cls.default_prohibitions()
    assert [(t.code, t.title, t.description, t.rules, t.prohibitions) for t in agent.tasks] == [
        (t.code, t.title, t.description, t.rules, t.prohibitions) for t in cls.default_tasks()
    ]
