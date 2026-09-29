# core/genai/rag/tokenizer.py
"""
語による検索(lexical_retriever)の語の切り出し。索引の断片と問いに同じ切り出しを使う。

- Tokenizer: 抽象の契約
- BigramTokenizer: 既定。追加の依存も辞書も要らない。全角・半角をそろえ(NFKC)小文字にしてから、
  英字等は単語、数値は小数点・千の位の区切り・%を含めて1語("0.25"・"3%")、日本語・中国語・韓国語の
  文字の並びは2文字ずつ(文字のbigram。1文字だけならその1文字)にする。未知語・複合語でも部分的に
  一致するが、関係の無い語の一部にも一致する(「京都」が「東京都」に)
- 形態素解析で切り出す具象は任意の依存を要するため、別のファイル(sudachi_tokenizer)に置く
"""

import abc
import re
import unicodedata

CJK_CHARS = "぀-ヿ㐀-䶿一-鿿豈-﫿가-힯ｦ-ﾟ"
_TOKEN = re.compile(
    rf"(?P<cjk>[{CJK_CHARS}]+)"
    r"|(?P<number>\d+(?:[.,]\d+)*%?)"
    rf"|(?P<word>[^\W\d_{CJK_CHARS}]+)"
)


def normalize(text: str) -> str:
    """全角・半角をそろえて(NFKC)小文字にする。"""
    return unicodedata.normalize("NFKC", text).lower()


def bigrams(run: str) -> list[str]:
    return [run] if len(run) == 1 else [run[i : i + 2] for i in range(len(run) - 1)]


class Tokenizer(abc.ABC):
    name: str = "tokenizer"

    @abc.abstractmethod
    def tokenize(self, text: str) -> list[str]:
        """textを検索の語の列にする(同じ語が複数回あれば、その回数だけ含める)。"""


class BigramTokenizer(Tokenizer):
    name = "bigram"

    def tokenize(self, text: str) -> list[str]:
        tokens: list[str] = []
        for match in _TOKEN.finditer(normalize(text)):
            if match.lastgroup == "cjk":
                tokens += self.cjk_tokens(match.group())
            else:
                tokens.append(match.group())
        return tokens

    def cjk_tokens(self, run: str) -> list[str]:
        """日本語・中国語・韓国語の文字の並び(句読点・英数字で区切られた1つながり)の語。"""
        return bigrams(run)
