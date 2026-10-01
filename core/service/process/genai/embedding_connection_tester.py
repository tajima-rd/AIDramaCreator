# core/service/process/genai/embedding_connection_tester.py
"""
埋め込み(Embedding)の設定で、実際に短い文章を埋め込めるかを確かめる(Preferencesの接続テスト)。
llama.cppは埋め込みを有効にして(--embeddings)起動したサーバーでないと失敗するため、保存前に試せるようにする。
保存前の設定を試せるよう、プロジェクトに保存された設定ではなく渡された設定を使う。
"""

import dataclasses
import time
from dataclasses import dataclass
from typing import Optional

from core.project.project import EmbeddingSetting, Project

from .generator_builder import build_embedding_generator

TEST_TEXT = "embedding connection test"


@dataclass
class EmbeddingConnectionTestOutcome:
    ok: bool
    message: str
    dimensions: Optional[int]  # 返ったベクトルの長さ
    elapsed_seconds: float


def check_embedding_connection(project: Project, setting: EmbeddingSetting) -> EmbeddingConnectionTestOutcome:
    """settingで生成器を作って短い文章を埋め込ませる。失敗しても例外にせず、理由を返す。"""
    start = time.perf_counter()
    try:
        generator = build_embedding_generator(dataclasses.replace(project, embedding=setting))
        vectors = generator.embed([TEST_TEXT], "query")
        if not vectors or not vectors[0]:
            raise ValueError("空の埋め込みが返されました。")
    except Exception as exc:  # 接続・認証・モデル名の誤り・埋め込みが無効なサーバー等、原因を問わず利用者に見せる
        return EmbeddingConnectionTestOutcome(
            ok=False,
            message=f"{type(exc).__name__}: {exc}",
            dimensions=None,
            elapsed_seconds=time.perf_counter() - start,
        )
    return EmbeddingConnectionTestOutcome(
        ok=True,
        message="埋め込めました。",
        dimensions=len(vectors[0]),
        elapsed_seconds=time.perf_counter() - start,
    )
