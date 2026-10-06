# core/model/agent/actor.py
"""Actor。台詞を音声にする演者。"""

from typing import Optional

from core.model.agent.agent_task import AgentTask
from core.model.agent.base_agent import BaseAgent


class LanguageVoice:
    """演者がある言語を読むときの声。languageは言語のコード(BCP 47)、voice_nameは話者(提供元の声の識別子)。
    提供元・モデルが空なら演者の既定(それも空ならproject.yamlのgenai.tts)。"""

    def __init__(
        self,
        language: str,
        voice_name: str,
        tts_provider: Optional[str] = None,
        tts_model: Optional[str] = None,
    ):
        self.language: str = language
        self.voice_name: str = voice_name
        self.tts_provider: Optional[str] = tts_provider
        self.tts_model: Optional[str] = tts_model


class Actor(BaseAgent):
    """配役(Cast)ごとに1つ。割り当てられた人物の台詞(Dialogue)を、演出と配役の演じ方に従って音声にする。
    人物になりきって台詞を考える者ではない。casting_idは演じる配役(ID参照)。音声合成の提供元(tts_provider)・モデル
    (tts_model)・話者(voice_name。提供元の声の識別子)を1組持つ(2026-10-02ユーザー決定。文章生成と仕事が違うため、
    「どの生成AIで動かすかはモデルに持たない」の例外。提供元・モデルが空ならproject.yamlのgenai.tts)。これが既定の声で、
    voicesは言語ごとの声(その言語を読むときに既定の声の代わりに使う。同じ言語は1つ。2026-10-06ユーザー)。"""

    def __init__(
        self,
        casting_id: str,
        name: str,
        voice_name: Optional[str] = None,
        tts_provider: Optional[str] = None,
        tts_model: Optional[str] = None,
        role: Optional[str] = None,
        persona: Optional[str] = None,
        rules: Optional[list[str]] = None,
        prohibitions: Optional[list[str]] = None,
        tasks: Optional[list[AgentTask]] = None,
        voices: Optional[list[LanguageVoice]] = None,
    ):
        super().__init__(name, role, persona, rules, prohibitions, tasks)
        self.casting_id: str = casting_id
        self.voice_name: Optional[str] = voice_name
        self.tts_provider: Optional[str] = tts_provider
        self.tts_model: Optional[str] = tts_model
        self.voices: list[LanguageVoice] = list(voices or [])
