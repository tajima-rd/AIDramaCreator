# core/genai/rag/sudachi_tokenizer.py
"""
日本語の形態素解析(SudachiPy)を使う語の切り出し。任意の依存(requirements/rag-ja.txt)。

日本語の文字の並びを、形態素の語と2文字ずつの語の両方にする(2026-09-29ユーザー決定)。形態素の語で
関係の無い語の一部への一致(「京都」が「東京都」に)を抑えつつ、分かち書きの誤り・辞書に無い語は
2文字ずつの語で拾う。英字・数値の扱いはBigramTokenizerと同じ。

- 形態素は長い単位(SplitMode.C。「腎臓病」「東京都」を1語)を既定にする。短い単位の部分は2文字ずつの
  語が補う
- 語は正規化した形(normalized_form。「附属」→「付属」)を使い、表記の揺れをそろえる
- 助詞・助動詞・記号・空白は語にしない(ほぼ全ての断片に現れ、検索の手がかりにならないため)
- 形態素の語には印(MORPHEME_PREFIX)を付け、同じ文字列の2文字ずつの語(「初期」)と別の語として数える
  (BM25で、それぞれの一致が別々に点数になる)。印は英字・数値・日本語の語に現れない文字にする
"""

from .tokenizer import BigramTokenizer

# 語にしない品詞(品詞の大分類)
SKIPPED_PARTS_OF_SPEECH = ("助詞", "助動詞", "補助記号", "空白")
MORPHEME_PREFIX = "m:"


class SudachiTokenizer(BigramTokenizer):
    name = "sudachi"

    def __init__(self, split_mode: str = "C", dictionary: str = "core", include_bigrams: bool = True):
        try:
            from sudachipy import Dictionary, SplitMode
        except ImportError as exc:
            raise ImportError(
                "SudachiTokenizerにはSudachiPyと辞書が必要です(pip install -r requirements/rag-ja.txt)。"
            ) from exc
        if split_mode not in ("A", "B", "C"):
            raise ValueError(f"split_modeはA・B・Cのどれかです: {split_mode}")
        self.split_mode = split_mode
        self.include_bigrams = include_bigrams
        self._tokenizer = Dictionary(dict=dictionary).tokenizer(mode=getattr(SplitMode, split_mode))

    def morphemes(self, run: str) -> list[str]:
        return [
            MORPHEME_PREFIX + m.normalized_form()
            for m in self._tokenizer.tokenize(run)
            if m.part_of_speech()[0] not in SKIPPED_PARTS_OF_SPEECH and m.normalized_form().strip()
        ]

    def cjk_tokens(self, run: str) -> list[str]:
        morphemes = self.morphemes(run)
        return morphemes + super().cjk_tokens(run) if self.include_bigrams else morphemes
