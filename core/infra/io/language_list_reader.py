# core/infra/io/language_list_reader.py
"""
作品の言語の一覧(システム既定。core/default/languages.yaml)を読む。Dramaturgy Editorの言語のプルダウンに使う。
"""

import os

import yaml

LANGUAGES_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "default", "languages.yaml")


class LanguageEntry:
    """codeはBCP 47の言語のコード(作品・訳文に保存する値)、nameはその言語での名前、labelは日本語の名前。"""

    def __init__(self, code: str, name: str, label: str):
        self.code: str = code
        self.name: str = name
        self.label: str = label


def read_languages() -> list[LanguageEntry]:
    with open(LANGUAGES_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return [LanguageEntry(str(item["code"]), str(item["name"]), str(item["label"])) for item in data.get("languages", [])]
