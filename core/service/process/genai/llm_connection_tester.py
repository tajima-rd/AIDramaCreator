# core/service/process/genai/llm_connection_tester.py
"""
文章生成(LLM)の設定で、実際に短い文章を生成できるかを確かめる(Preferencesの接続テスト)。
保存前の設定を試せるよう、プロジェクトに保存された設定ではなく渡された設定を使う。
"""

import dataclasses
import time
from dataclasses import dataclass

from core.project.project import LlmSetting, Project

from .generator_builder import build_text_generator

TEST_PROMPT = "Reply with the single word: OK"


@dataclass
class LlmConnectionTestOutcome:
    ok: bool
    message: str
    response_text: str | None
    elapsed_seconds: float


def check_llm_connection(project: Project, setting: LlmSetting) -> LlmConnectionTestOutcome:
    """settingで生成器を作って短い文章を生成させる。失敗しても例外にせず、理由を返す。"""
    start = time.perf_counter()
    try:
        generator = build_text_generator(dataclasses.replace(project, llm=setting))
        text = generator.generate(TEST_PROMPT)
    except Exception as exc:  # 接続・認証・モデル名の誤り等、原因を問わず利用者に見せる
        return LlmConnectionTestOutcome(
            ok=False,
            message=f"{type(exc).__name__}: {exc}",
            response_text=None,
            elapsed_seconds=time.perf_counter() - start,
        )
    return LlmConnectionTestOutcome(
        ok=True,
        message="生成できました。",
        response_text=text,
        elapsed_seconds=time.perf_counter() - start,
    )
