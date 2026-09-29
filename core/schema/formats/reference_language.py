# core/schema/formats/reference_language.py
"""
参考資料の言語と、資料の検索で使う決まった問いの訳のファイル形式。資料ごとに
datasets/.index/<ファイル名>.language.yaml に置く(core.infra.store.dataset_file_store.language_path)。

資料の検索(core.service.process.genai.reference_searcher)が、語による検索を資料の言語で行うために使う。
言語の判定と問いの訳は生成AIが行い、資料が変わる(source_hashが違う)まで使い回す。
"""

from pydantic import BaseModel


class ReferenceLanguage(BaseModel):
    source_hash: str  # 判定した資料の中身のハッシュ(core.genai.rag.chunk_index.content_hash)
    language: str  # 資料の主な言語の英語での名前("English"・"Japanese"等)
    queries: dict[str, str] = {}  # 決まった問い(英語)→資料の言語に訳した問い
