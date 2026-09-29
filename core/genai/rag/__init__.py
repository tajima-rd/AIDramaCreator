# core/genai/rag
"""
資料の検索(RAG: Retrieval-Augmented Generation)。資料を丸ごと渡す代わりに、問いに近い部分だけを
場所付きで生成AIに渡すための部品。genaiと同じく、使う側のコードに依存しない。

- chunk: 資料の構成要素(Block)と検索の単位(Chunk)の型
- document_reader: PDF・DOCX・XLSX・CSVから場所付きのBlockの列/資料全体のテキストを取り出す
- document_chunker: Blockの列を検索の単位に分ける(表は見出しの行と題を保つ)
- chunk_index: 1つの資料の索引(断片と埋め込み)。保存先は使う側がパスで渡す
- retriever: 検索の抽象。lexical_retriever(BM25)・embedding_retriever(埋め込み)・
  hybrid_retriever(順位の統合)が具象
- tokenizer: 語による検索の語の切り出し(既定は2文字ずつのBigramTokenizer)。sudachi_tokenizerは
  日本語の形態素解析(SudachiPy、任意の依存)。sudachi_tokenizerはここではimportしない
- query_language: 問いと資料の言語が違うかの見積もり(文字の種類と語の一致の割合。生成AIを使わない)
- context_builder: 検索の結果から生成AIに渡す文脈を組み立てる
- factory: 索引(index_document)と検索(create_retriever)の既定の組み立て

使い方:
    index = index_document("paper.pdf", data, "pdf", embedder=embedder)  # embedderは任意
    index.save(path)  # 以後はChunkIndex.load(path)。index.is_current(data)で資料の変更を確かめる
    hits = create_retriever([index], embedder).search("問い", top_k=8)  # 日本語の資料はtokenizer=SudachiTokenizer()
    context = build_context(hits)
    hits = search_many(create_retriever([index], embedder), ["問い1", "問い2"], top_k=20)  # 複数の問いを統合
"""

from .chunk import Block, Chunk
from .chunk_index import ChunkIndex
from .context_builder import build_context
from .document_chunker import chunk_blocks
from .document_reader import document_blocks, document_text
from .embedding_retriever import EmbeddingRetriever
from .factory import create_retriever, index_document
from .hybrid_retriever import HybridRetriever, search_many
from .lexical_retriever import LexicalRetriever
from .query_language import language_differs
from .retriever import Retriever, SearchHit
from .tokenizer import BigramTokenizer, Tokenizer

__all__ = [
    "BigramTokenizer",
    "Block",
    "Chunk",
    "ChunkIndex",
    "EmbeddingRetriever",
    "HybridRetriever",
    "LexicalRetriever",
    "Retriever",
    "SearchHit",
    "Tokenizer",
    "build_context",
    "chunk_blocks",
    "create_retriever",
    "document_blocks",
    "document_text",
    "index_document",
    "language_differs",
    "search_many",
]
