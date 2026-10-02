# core/prompt/ai_build/common.py
"""Build with AIの全工程に共通する、モード・応答の部品・規則。"""

from enum import StrEnum

from pydantic import BaseModel, Field


class BuildMode(StrEnum):
    ONE_SHOT = "one_shot"  # ワンショット下書き: 工程の内容を1回で丸ごと提案する
    DIALOGUE = "dialogue"  # 対話: 相談しながら、必要なときだけ変える部分を提案する


class EvidenceItem(BaseModel):
    target: str = Field(description="根拠を示す項目の名前(例: 企画意図)")
    source: str = Field(
        description="根拠にした資料の名前と箇所(ページ等)。利用者の発言なら「利用者の発言」"
    )
    quote: str = Field(description="根拠の文の引用。短く")


# 生成AIへの共通の規則。構造化出力は提供元(手元のllama.cpp等)によって省略可能な項目の扱いが違うため、応答の型の項目は
# すべて必須にし、無い値は空文字・空の一覧で返させる
COMMON_RULES = [
    "返事(message)は、利用者の最新の発言と同じ言語で書く。",
    "資料や利用者の発言に基づく内容には、根拠(evidence)を示す。創作した内容に根拠は要らない。",
    "利用者に確かめたいことは、質問(questions)に1つずつ書く。",
    "提案は必ず応答の提案の欄(proposal・characters・groups・relationships等)に入れる。返事(message)の中に提案の全文を書くだけにしない。",
    "識別子(id・key)は書かない。",
]

ONE_SHOT_RULES = [
    "利用者の要望・資料・今の内容から、この工程の内容を1回で丸ごと作り、has_proposalをtrueにする。",
    "今の内容に良いところがあれば活かす。決められない項目は空文字にする。",
    "返事(message)には、作った内容の要点と、利用者が確かめるとよい点を短く書く。",
]

DIALOGUE_RULES = [
    "利用者と相談する。考えや選択肢を示し、利用者の判断を助ける。",
    "内容を変える提案があるときだけhas_proposalをtrueにし、proposalに提案した後の内容の全体(変えない項目は今の値のまま)を入れる。",
    "提案が無いときはhas_proposalをfalseにし、proposalには今の内容をそのまま入れる。",
    "利用者が求めていない項目を勝手に変えない。",
]
