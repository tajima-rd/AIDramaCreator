# core/prompt/ai_build/step.py
"""
Build with AIの工程(右側のタブ)と、相談相手のエージェント・タスクの対応表(QIDMのSTEP_PROMPTSにあたる)。
チャットは今開いているタブの工程に結び付く。プロンプトの無い工程(available=False)は、タブを並べるが選べない。
"""


class BuildStep:
    """keyは工程の識別子(会話の記録にも使う)、role_nameは相談相手の職能(モデル定義YAMLの区画名の単数形)、
    task_codeはそのタスク(AgentTask.code)。"""

    def __init__(self, key: str, label: str, role_name: str, task_code: str, available: bool):
        self.key: str = key
        self.label: str = label
        self.role_name: str = role_name
        self.task_code: str = task_code
        self.available: bool = available


# 並びがタブの順。工程を足すときは、ここと、工程のプロンプト(このパッケージ)と、提案の反映(ai_builder)を足す
BUILD_STEPS: list[BuildStep] = [
    BuildStep("proposal", "Proposal", "scriptwriter", "draft_proposal", True),
    BuildStep("characters", "Characters", "scriptwriter", "create_character", True),
    BuildStep("groups", "Groups", "scriptwriter", "create_character_group", True),
    BuildStep("relationships", "Relationships", "scriptwriter", "create_relationship", True),
    BuildStep("casting", "Casting", "casting_director", "cast_character", True),
    BuildStep("audition", "Audition", "casting_director", "assign_voice", True),
]


def find_step(key: str) -> BuildStep:
    """工程(使えないものはValueError)。"""
    step = next((s for s in BUILD_STEPS if s.key == key), None)
    if step is None:
        raise ValueError(f"工程 '{key}' はありません")
    if not step.available:
        raise ValueError(f"工程 '{step.label}' はまだ用意していません")
    return step
