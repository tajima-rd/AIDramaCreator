# core/model/agent/agent_task.py
"""
エージェントのタスク(職務の定義)。エージェントが担う仕事の1つで、生成AIへのプロンプトを組み立てるための情報
(説明・厳守事項・禁止事項)を持つ(2026-10-01ユーザー決定)。プロンプトの文そのもの・応答の型・渡す情報の範囲は持たず、
codeでcore.promptの側と結び付ける。発注(誰に・いつ・状態・結果)ではない(エージェントどうしのやり取りは処理の側。
docs/future_design.md「対話方式の制作」)。
"""

from typing import Optional


class AgentTask:
    """codeはタスクの識別子(職能ごとにシステム既定(core/default/agents/)で決まり、変わらない)。title・description・rules・prohibitionsは文面で、
    作品ごとに書き換えられる。"""

    def __init__(
        self,
        code: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        rules: Optional[list[str]] = None,
        prohibitions: Optional[list[str]] = None,
    ):
        self.code: str = code
        self.title: Optional[str] = title
        self.description: Optional[str] = description
        self.rules: list[str] = list(rules or [])
        self.prohibitions: list[str] = list(prohibitions or [])
