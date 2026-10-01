# core/genai/rag/factory.py
"""
資料の索引と検索の既定の組み立て。

- index_document: 資料(バイト列と形式)をテキスト化・分割して索引を作る。埋め込みの生成器を渡せば
  断片も埋め込む
- create_retriever: 索引の列から検索を作る。埋め込みの生成器があれば語による検索と埋め込みによる
  検索を順位で統合し、無ければ語による検索だけにする(埋め込みのモデルが無い環境でも動く)。語の切り出し
  (tokenizer)は既定で2文字ずつ(BigramTokenizer)。日本語の資料にはSudachiTokenizerを渡せる
"""

from typing import Optional

from ..generator import EmbeddingGenerator
from .chunk_index import ChunkIndex, content_hash
from .document_chunker import DEFAULT_MAX_CHARS, DEFAULT_OVERLAP_CHARS, chunk_blocks
from .document_reader import document_blocks
from .embedding_retriever import EmbeddingRetriever
from .hybrid_retriever import HybridRetriever
from .lexical_retriever import LexicalRetriever
from .retriever import Retriever
from .tokenizer import Tokenizer


def index_document(
    source: str,
    data: bytes,
    file_format: str,
    *,
    embedder: Optional[EmbeddingGenerator] = None,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap: int = DEFAULT_OVERLAP_CHARS,
) -> ChunkIndex:
    chunks = chunk_blocks(document_blocks(data, file_format), source, max_chars=max_chars, overlap=overlap)
    index = ChunkIndex(source=source, chunks=chunks, source_hash=content_hash(data))
    return index.with_embeddings(embedder) if embedder is not None else index


def create_retriever(
    indexes: list[ChunkIndex],
    embedder: Optional[EmbeddingGenerator] = None,
    tokenizer: Optional[Tokenizer] = None,
) -> Retriever:
    lexical = LexicalRetriever(indexes, tokenizer)
    if embedder is None:
        return lexical
    return HybridRetriever([lexical, EmbeddingRetriever(indexes, embedder)])
