# core/service/api/language.py
"""作品の言語の一覧の公開API(システム既定。Dramaturgy Editorの言語のプルダウンに使う)。"""

from core.infra.io.language_list_reader import read_languages
from core.schema.api.language import LanguageInfo, LanguageListResult


def list_languages() -> LanguageListResult:
    return LanguageListResult(
        languages=[LanguageInfo(code=e.code, name=e.name, label=e.label) for e in read_languages()]
    )
