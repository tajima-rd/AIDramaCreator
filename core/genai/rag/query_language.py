# core/genai/rag/query_language.py
"""
問いと資料の言語が違うかの見積もり(生成AIを使わない)。

語による検索は、問いと資料の言語が違うと一致しない。違うときだけ使う側が問いを資料の言語にする
(生成AIに訳させる等)ために、安く見積もる:

- 文字の種類(scripts): 問いの文字の種類(ラテン文字・かな・漢字・ハングル等)が資料に無ければ違う
  (日本語の問いと英語の資料)。資料の側は少しでも現れれば含める(日本語の論文の中の英語の語等)
- 語の一致の割合(LexicalRetriever.coverage): 同じ種類の文字の別の言語(英語とドイツ語等)は、問いの語が
  資料にほとんど現れないことで見分ける。語を空白で区切る文字の問いで、語が3つ以上のときだけ使う
  (漢字・かなの2文字ずつの語は、同じ日本語でも話し言葉の言い回しが論文に現れず、短い問いは語が少なすぎて
  割合が当てにならない)。漢字・かな・ハングルどうしは文字の種類だけで見分ける(日本語と中国語はかなの有無)

見積もりなので、同じ言語でも「違う」と判定することがある(問いの語が資料に無い言い回しばかりの場合)。
その場合も訳した問いが同じ言語になるだけで、検索の結果は悪くならない。
"""

from collections import Counter

from ..character_check import script
from .chunk_index import ChunkIndex
from .lexical_retriever import LexicalRetriever

QUERY_SCRIPT_SHARE = 0.2  # 問いの文字の種類として数える割合
DOCUMENT_SCRIPT_SHARE = 0.02  # 資料の文字の種類として数える割合
MIN_COVERAGE = 0.2  # これより問いの語が資料に現れなければ、言語が違うとみなす
MIN_TERMS_FOR_COVERAGE = 3
UNSPACED_SCRIPTS = frozenset({"CJK", "KANA", "HANGUL"})  # 語の一致の割合では見分けない文字


def scripts(text: str, min_share: float) -> set[str]:
    """textの文字のうち、min_share以上を占める文字の種類。"""
    counts = Counter(s for s in map(script, text) if s is not None)
    total = sum(counts.values())
    return {s for s, n in counts.items() if n / total >= min_share} if total else set()


def document_scripts(index: ChunkIndex) -> set[str]:
    return scripts("".join(c.text for c in index.chunks), DOCUMENT_SCRIPT_SHARE)


def language_differs(query: str, index: ChunkIndex, lexical: LexicalRetriever) -> bool:
    """問いが資料と違う言語で書かれていそうか(問いに文字が無ければFalse)。"""
    query_scripts = scripts(query, QUERY_SCRIPT_SHARE)
    if not query_scripts:
        return False
    if not query_scripts <= document_scripts(index):
        return True
    if query_scripts & UNSPACED_SCRIPTS or len(set(lexical.tokenizer.tokenize(query))) < MIN_TERMS_FOR_COVERAGE:
        return False
    return lexical.coverage(query, index.source) < MIN_COVERAGE
