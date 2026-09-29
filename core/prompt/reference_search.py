# core/prompt/reference_search.py
"""
参考資料の検索(core.service.process.genai.reference_searcher)で、問いを資料の言語にするためのプロンプト。

語による検索は、問いと資料の言語が違うと一致しない。そのため:

- 資料ごとに1回、資料の冒頭から主な言語を判定させ、決まった問い(英語)をその言語に訳させる(保存して使い回す)
- 利用者の発言が資料と違う言語で書かれていそうなとき(core.genai.rag.language_differs)だけ、資料の言語で
  検索語を作らせる

どちらも資料の中身を答えさせるのではなく、検索の問いを作らせるだけ。分野の言葉は使わない。
"""

from pydantic import BaseModel, Field

from core.genai.prompt import BulletInstruction, Prompt, Section

# 言語の判定に渡す資料の冒頭の長さ
LANGUAGE_SAMPLE_CHARS = 2000

LANGUAGE_INSTRUCTIONS = [
    "You receive the beginning of a document and a list of search queries written in English.",
    "Identify the main language of the document (the language of its body text, not of occasional "
    "terms or references). Give its name in English, for example 'English' or 'Japanese'.",
    "Translate every search query into that language, in the same order. Keep each one a short search "
    "query and use the terms a document in that language would use. If the language is English, return "
    "the queries unchanged.",
    "Do not answer the queries.",
]

# 生成AIは作業の依頼(「Featureを提案して」)を話題と取り違え、"feature proposal guidelines"のような
# 資料と関係の無い検索語を作った(2026-09-29、Gemma 4)。それが資料の必要な表を文脈から押し出したため、
# 作業の言葉を話題にしないこと・話題が無ければ返さないことを明示し、今探しているものを手がかりに渡す
SEARCH_TERMS_INSTRUCTIONS = [
    "You receive a user's message to an assistant that builds a model from reference documents, what the "
    "assistant is looking for in the documents in the current step, and a list of languages of the documents.",
    "Requests about the assistant's work (for example to propose, check or revise something) and the names of "
    "the parts of the model being built (for example Domain, Feature, Factor) are not topics of the documents. "
    "Never write queries about them.",
    "Find the topics of the documents that the message refers to (things, conditions, groups, measurements, "
    "periods, tables). Combine them with what is being looked for in the current step.",
    "For each language, write one to three short search queries in that language, using the terms a document "
    "in that language would use, not a literal translation. If the message refers to no topic of the "
    "documents, return no queries.",
    "Do not answer the message.",
]


class ReferenceLanguageResponse(BaseModel):
    language: str = Field(description="Main language of the document, in English (e.g. 'English', 'Japanese')")
    queries: list[str] = Field(description="The search queries translated into that language, in the same order")


class LanguageQuery(BaseModel):
    language: str = Field(description="One of the given languages, exactly as given")
    query: str


class SearchTermsResponse(BaseModel):
    queries: list[LanguageQuery]


def language_prompt() -> Prompt:
    return Prompt(components=[Section(title="Task", children=[BulletInstruction(items=LANGUAGE_INSTRUCTIONS)])])


def language_request(sample: str, queries: list[str]) -> str:
    listed = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(queries))
    return f"## Beginning of the document\n{sample[:LANGUAGE_SAMPLE_CHARS]}\n\n## Search queries\n{listed}"


def translation_request(language: str, queries: list[str]) -> str:
    """言語が分かっている資料に、決まった問いを追加で訳させる(判定は済んでいるので冒頭は渡さない)。"""
    listed = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(queries))
    return f"## Main language of the document\n{language}\n\n## Search queries\n{listed}"


def search_terms_prompt() -> Prompt:
    return Prompt(components=[Section(title="Task", children=[BulletInstruction(items=SEARCH_TERMS_INSTRUCTIONS)])])


def search_terms_request(message: str, languages: list[str], looking_for: list[str] | tuple[str, ...] = ()) -> str:
    looking = "\n".join(f"- {q}" for q in looking_for) or "(not specified)"
    return (
        f"## User's message\n{message}\n\n## Looked for in the current step\n{looking}\n\n"
        "## Languages of the documents\n" + "\n".join(languages)
    )
