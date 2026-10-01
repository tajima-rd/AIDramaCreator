# tests/api/test_agent_default.py
"""エージェントのユーザー既定(プロジェクトごと。api/routers/agent_default.py)。"""

import shutil
from pathlib import Path

import yaml

from core.infra.io.agent_default_reader import USER_DEFAULT_ROLES, system_default
from tests.conftest import parse_yaml


def _base(project) -> str:
    return f"/projects/{project.project_id}/agent-defaults"


def test_project_creation_copies_the_system_defaults(project):
    agents_dir = Path(project.layout.user_default_agents_dir)
    assert sorted(p.stem for p in agents_dir.glob("*.yaml")) == sorted(USER_DEFAULT_ROLES)


def test_list_returns_every_role_completed(client, project):
    resp = client.get(_base(project))
    assert resp.status_code == 200
    defaults = parse_yaml(resp)["defaults"]
    assert list(defaults) == list(USER_DEFAULT_ROLES)  # Actorは含まない
    writer = defaults["scriptwriter"]
    assert writer["role"] == system_default("scriptwriter").role
    assert [t["code"] for t in writer["tasks"]] == [
        t.code for t in system_default("scriptwriter").tasks
    ]


def test_save_and_restore_user_default(client, project):
    body = {
        "name": "うちの脚本家",
        "persona": "落ち着いた語り口",
        "prohibitions": [],
        "tasks": [{"code": "write_dialogue", "rules": ["但馬の方言で書く。"]}],
    }
    resp = client.put(
        f"{_base(project)}/scriptwriter", content=yaml.safe_dump(body, allow_unicode=True)
    )
    assert resp.status_code == 200
    saved = parse_yaml(client.get(_base(project)))["defaults"]["scriptwriter"]
    assert (saved["name"], saved["persona"], saved["prohibitions"]) == (
        "うちの脚本家",
        "落ち着いた語り口",
        [],
    )
    # 省略した項目はシステム既定で補って全文を書く
    assert saved["rules"] == system_default("scriptwriter").rules
    dialogue = next(t for t in saved["tasks"] if t["code"] == "write_dialogue")
    assert dialogue["rules"] == ["但馬の方言で書く。"]

    resp = client.post(f"{_base(project)}/scriptwriter/restore")
    assert resp.status_code == 200
    restored = parse_yaml(client.get(_base(project)))["defaults"]["scriptwriter"]
    assert restored["name"] == system_default("scriptwriter").name
    assert restored["prohibitions"] == system_default("scriptwriter").prohibitions


def test_unknown_role_and_task_are_refused(client, project):
    assert client.put(f"{_base(project)}/actor", content="name: 演者\n").status_code == 400
    assert client.post(f"{_base(project)}/producer/restore").status_code == 400
    bad = "name: 脚本家\ntasks: [{code: nope}]\n"
    assert client.put(f"{_base(project)}/scriptwriter", content=bad).status_code == 400


def test_project_without_user_defaults_gets_them_on_first_use(client, project):
    shutil.rmtree(Path(project.layout.user_default_agents_dir).parent)
    resp = client.get(_base(project))
    assert resp.status_code == 200
    assert list(parse_yaml(resp)["defaults"]) == list(USER_DEFAULT_ROLES)
