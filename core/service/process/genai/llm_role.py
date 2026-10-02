# core/service/process/genai/llm_role.py
"""
文章生成の2つの役割(作品作り・作業補助)と、タスクごとにどちらを使うかの対応表。

- creative(作品作り): 台詞・演出等、品質が要るタスク。課金のある高機能な生成AIを想定(Project.creative_llm)
- assistive(作業補助): 骨組みの作成等、課金の無い生成AI(Gemma・手元のllama.cpp等)で足りるタスク(Project.assistive_llm)

タスクはエージェントのタスクの識別子(AgentTask.code。core/default/agents/)で示す。エージェントに属さない処理も、
同じ名前空間のcodeをここに足す。どの生成AIで動かすかはモデル(core.model)に持たず、処理の側のこの表で決める
(docs/model_design.md)。タスクを足す・役割を移すときは、この表だけを直す。表に無いタスクはエラーにする
(黙って課金のある生成AIで動かさないため)。
"""

from enum import StrEnum


class LlmRole(StrEnum):
    CREATIVE = "creative"  # 作品作り
    ASSISTIVE = "assistive"  # 作業補助


# タスク(AgentTask.code)→ 使う文章生成の役割。Actorのperform_dialogueは音声合成なので載せない
TASK_LLM_ROLES: dict[str, LlmRole] = {
    # Scriptwriter
    "draft_proposal": LlmRole.CREATIVE,
    "create_character": LlmRole.CREATIVE,
    "create_character_group": LlmRole.CREATIVE,  # Build with AIのGroupsの工程(2026-10-02)
    "create_relationship": LlmRole.CREATIVE,  # Build with AIのRelationshipsの工程(2026-10-02)
    "import_proposal_character": LlmRole.ASSISTIVE,  # 企画書の登場人物から骨組みを作る・統合する(2026-10-02)
    "check_character_conflict": LlmRole.ASSISTIVE,  # 登録済みの人物と企画書の矛盾を確かめる(2026-10-02)
    "write_synopsis": LlmRole.CREATIVE,
    "write_dialogue": LlmRole.CREATIVE,
    # Director
    "direct_scene": LlmRole.CREATIVE,
    # CastingDirector
    "cast_character": LlmRole.CREATIVE,
    "assign_voice": LlmRole.CREATIVE,
    # Researcher
    "answer_question": LlmRole.CREATIVE,
    "check_consistency": LlmRole.CREATIVE,
    # StageManager
    "translate": LlmRole.CREATIVE,
    # SoundEngineer
    "design_sound": LlmRole.CREATIVE,
}


def llm_role_for_task(task_code: str) -> LlmRole:
    """タスクに使う文章生成の役割。表に無いタスクはValueError。"""
    role = TASK_LLM_ROLES.get(task_code)
    if role is None:
        raise ValueError(f"タスク '{task_code}' に使う生成AI(作品作り・作業補助)が決まっていません(llm_role.TASK_LLM_ROLES)。")
    return role
