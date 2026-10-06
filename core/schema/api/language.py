# core/schema/api/language.py
"""作品の言語の一覧(core.service.api.language)のDTO。"""

from pydantic import BaseModel


class LanguageInfo(BaseModel):
    code: str  # BCP 47の言語のコード(例: ja・en・zh-CN)
    name: str  # その言語での名前
    label: str  # 日本語の名前


class LanguageListResult(BaseModel):
    languages: list[LanguageInfo]
