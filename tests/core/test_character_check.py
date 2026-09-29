# tests/core/test_character_check.py
"""
生成AIの出力の疑わしい文字の判定(core.genai.character_check)。

- 読めない文字の印・制御文字・見えない文字・私用領域は、出典に関係なく直すべき文字(blocking)
- 出典(資料・発言)に無い記号は疑う(認めることもできる)。出典にある記号、よく使う句読点、出典に同じ種類の
  文字がある文字(日本語の発言があれば日本語の説明)は疑わない。見た目の似た別の種類の文字は疑う
"""

from core.genai.character_check import Sources, find_character_issues


def _issues(text, sources=None, accepted=frozenset()):
    return [(i.char, i.reason, i.blocking) for i in find_character_issues(text, sources, accepted)]


def test_blocking_characters():
    assert _issues("a​b�\x07\tc\n") == [
        ("​", "invisible", True),
        ("�", "unreadable", True),
        ("", "private_use", True),
        ("\x07", "control", True),
    ]
    assert _issues("a​b", accepted={"​"}) == [("​", "invisible", True)]  # 認めても外さない


def test_characters_not_in_sources():
    sources = Sources.of(["baseline eGFR ≥35 mL/min – CKD", "Featureを提案してください。"])
    assert _issues("baseline eGFR ╦′ 35 ╦", sources) == [("╦", "not_in_sources", False), ("′", "not_in_sources", False)]
    assert _issues("eGFR ≥ 35 “quoted” — ok… 病期の進行、ステージ", sources) == []
    assert _issues("Сtage", sources) == [("С", "not_in_sources", False)]  # キリル文字のС(英字のCに似る)
    assert _issues("±5%", sources, accepted={"±"}) == []
    assert _issues("╦") == []  # 出典が無ければ文字の種類だけで判定する
