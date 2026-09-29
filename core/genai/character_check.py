# core/genai/character_check.py
"""
生成AIの出力に含まれる、疑わしい文字の判定。使う側のコードに依存しない。

生成AIは、資料の「≥」を「╦′」のような場違いな文字で書くことがある(2026-09-29、Gemma 4)。これは文字コードの
読み違い(文字化け)ではなく、どの文字コードの組み合わせでも再現しない。しかもその文字が次の入力に入ると、
生成AIの構造化出力が繰り返しに陥って終わらなくなった。判定は2種類:

- 文字の種類(常に直すべきもの。blocking=True): 読めなかった文字の印(U+FFFD)・制御文字(タブ・改行を除く)・
  見えない文字(ゼロ幅スペース等、カテゴリCf)・私用領域(Co)・未割り当て(Cn)・サロゲート(Cs)
- 出典との照合(blocking=False。正しい記号のこともある): 記号・句読点・英数字以外の数字などの文字が出典
  (資料・利用者の発言)に一度も現れない。文字は、その文字の種類(ラテン文字・かな・キリル文字等)が出典に
  無いときだけ疑う(日本語で書かれた説明を、英語の資料で疑わないように。見た目の似た別の文字の混入は捕まえる)。
  よく使う句読点(ダッシュ・引用符・三点リーダー・日本語の句読点・全角の英数記号)は照合しない
"""

import unicodedata
from dataclasses import dataclass

REPLACEMENT_CHARACTER = "�"
ALLOWED_CONTROLS = frozenset("\t\n\r")
BLOCKING_CATEGORIES = {"Cc": "control", "Cf": "invisible", "Co": "private_use", "Cn": "unassigned", "Cs": "unassigned"}
# 出典に無くても疑わない、文章でよく使う句読点(一般句読点のダッシュ・引用符・リーダー等、CJKの記号と句読点、
# 中黒、全角の英数記号)
COMMON_PUNCTUATION_RANGES = ((0x2010, 0x2027), (0x3000, 0x303F), (0x30FB, 0x30FB), (0xFF01, 0xFF5E))

REASON_TEXTS = {
    "unreadable": "読めなかった文字の印",
    "control": "制御文字",
    "invisible": "見えない文字",
    "private_use": "私用領域の文字(フォント固有の記号等)",
    "unassigned": "割り当ての無い文字",
    "not_in_sources": "資料にも発言にも無い文字",
}


@dataclass(frozen=True)
class CharacterIssue:
    char: str
    reason: str  # REASON_TEXTSのキー
    blocking: bool  # Trueなら直す必要がある(Falseは利用者が認めればそのままでよい)

    @property
    def codepoint(self) -> str:
        return f"U+{ord(self.char):04X}"

    @property
    def name(self) -> str:
        return unicodedata.name(self.char, "")


def script(char: str) -> str | None:
    """文字の種類(Unicodeの文字名の最初の語。ひらがな・カタカナはKANA)。文字でなければNone。"""
    if not unicodedata.category(char).startswith("L"):
        return None
    name = unicodedata.name(char, "")
    first = name.split(" ", 1)[0] if name else "OTHER"
    # 長音記号「ー」の名前は"KATAKANA-HIRAGANA PROLONGED SOUND MARK"
    kana = first.split("-", 1)[0] in ("HIRAGANA", "KATAKANA") or name.startswith("HALFWIDTH KATAKANA")
    return "KANA" if kana else first


def _is_common_punctuation(char: str) -> bool:
    code = ord(char)
    return any(low <= code <= high for low, high in COMMON_PUNCTUATION_RANGES)


def _blocking_reason(char: str) -> str | None:
    if char == REPLACEMENT_CHARACTER:
        return "unreadable"
    if char in ALLOWED_CONTROLS:
        return None
    return BLOCKING_CATEGORIES.get(unicodedata.category(char))


@dataclass(frozen=True)
class Sources:
    """出典(資料・利用者の発言)に現れる文字と文字の種類。"""

    chars: frozenset[str]
    scripts: frozenset[str]

    @classmethod
    def of(cls, texts: list[str]) -> "Sources":
        chars = frozenset(c for text in texts for c in text)
        return cls(chars, frozenset(s for s in map(script, chars) if s is not None))

    def has(self, char: str) -> bool:
        if char in self.chars:
            return True
        char_script = script(char)
        return char_script is not None and char_script in self.scripts


def find_character_issues(
    text: str, sources: Sources | None = None, accepted: frozenset[str] | set[str] = frozenset()
) -> list[CharacterIssue]:
    """textの疑わしい文字(同じ文字は1回、現れた順)。sourcesが無ければ文字の種類だけで判定する。
    acceptedの文字は出典との照合では疑わない(利用者が認めた記号。文字の種類の判定は外さない)。"""
    issues: list[CharacterIssue] = []
    seen: set[str] = set()
    for char in text:
        if char in seen:
            continue
        seen.add(char)
        reason = _blocking_reason(char)
        if reason is not None:
            issues.append(CharacterIssue(char, reason, True))
        elif (
            sources is not None
            and not char.isascii()
            and char not in accepted
            and not _is_common_punctuation(char)
            and not sources.has(char)
        ):
            issues.append(CharacterIssue(char, "not_in_sources", False))
    return issues
