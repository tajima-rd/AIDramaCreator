# tests/core/test_default_agents.py
"""
エージェントのシステム既定(core/default/agents/。職能ごとに1ファイル。core.infra.io.agent_default_reader)。
"""

import pytest

from core.infra.io.agent_default_reader import (
    SYSTEM_DEFAULT_DIR,
    SYSTEM_DEFAULT_ROLES,
    complete_agent_spec,
    parse_agent_default,
    system_default,
)
from core.infra.io.model_definition_reader import build_model_definition_from_yaml
from core.model.agent import Actor
from core.model.agent.factory import AGENT_ROLES
from core.schema.formats.dramaturgy_definition import AgentSpec


def test_every_role_has_a_system_default():
    assert sorted(p.stem for p in SYSTEM_DEFAULT_DIR.glob("*.yaml")) == sorted(SYSTEM_DEFAULT_ROLES)


@pytest.mark.parametrize("role_name", SYSTEM_DEFAULT_ROLES)
def test_system_default_is_complete(role_name):
    default = system_default(role_name)
    assert default.name and default.role
    assert default.rules is not None and default.prohibitions is not None
    codes = [t.code for t in default.tasks]
    assert codes and len(codes) == len(set(codes))
    assert all(t.title and t.description for t in default.tasks)


@pytest.mark.parametrize("role_name", sorted(AGENT_ROLES))
def test_system_default_file_can_be_overlaid_on_a_dramaturgy(role_name):
    text = (SYSTEM_DEFAULT_DIR / f"{role_name}.yaml").read_text(encoding="utf-8")
    (agent,) = build_model_definition_from_yaml(
        "dramaturgy: {title: 既定の確認}\n", text
    ).dramaturgy.agents
    assert type(agent) is AGENT_ROLES[role_name]
    default = system_default(role_name)
    assert (agent.role, agent.rules, agent.prohibitions) == (
        default.role,
        default.rules,
        default.prohibitions,
    )


def test_omitted_items_are_completed_from_the_system_default():
    spec = AgentSpec(
        name="脚本家",
        prohibitions=[],
        tasks=[{"code": "write_dialogue", "rules": ["方言で書く。"]}],
    )
    full = complete_agent_spec("scriptwriter", spec)
    default = system_default("scriptwriter")
    assert (full.role, full.rules, full.prohibitions) == (default.role, default.rules, [])
    assert [t.code for t in full.tasks] == [t.code for t in default.tasks]
    dialogue = next(t for t in full.tasks if t.code == "write_dialogue")
    assert dialogue.rules == ["方言で書く。"] and dialogue.title is not None
    assert spec.role is None  # 元のspecは変えない


@pytest.mark.parametrize(
    "tasks, message",
    [
        ([{"code": "nope"}], "タスク 'nope'"),
        ([{"code": "write_dialogue"}, {"code": "write_dialogue"}], "重複"),
    ],
)
def test_unknown_or_duplicated_task_codes_are_refused(tasks, message):
    with pytest.raises(ValueError, match=message):
        complete_agent_spec("scriptwriter", AgentSpec(name="脚本家", tasks=tasks))


def test_parse_refuses_other_shapes():
    with pytest.raises(ValueError, match="dramaturgy.agents.scriptwriters"):
        parse_agent_default("dramaturgy: {agents: {directors: [{name: 演出家}]}}", "scriptwriter")
    with pytest.raises(ValueError, match="1人だけ"):
        parse_agent_default(
            "dramaturgy: {agents: {scriptwriters: [{name: a}, {name: b}]}}", "scriptwriter"
        )


def test_actor_default_completes_actors_in_model_definitions():
    text = """
dramaturgy:
  title: 題
  casts: [{key: c, character: {ref: p}}]
  agents: {actors: [{name: 演者, cast: {ref: c}}]}
characters: [{key: p, name: 人}]
"""
    (actor,) = build_model_definition_from_yaml(text).dramaturgy.agents
    assert isinstance(actor, Actor)
    assert [t.code for t in actor.tasks] == [t.code for t in system_default("actor").tasks]
