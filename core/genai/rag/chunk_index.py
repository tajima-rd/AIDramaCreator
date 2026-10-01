# core/genai/rag/chunk_index.py
"""
1つの資料の索引(ChunkIndex): 断片(Chunk)の列と、あれば断片ごとの埋め込み。

- 索引は資料ごとに作る(資料の追加・更新・削除に索引を合わせやすいように)。複数の資料を探すときは
  検索(retriever)に索引の列を渡す
- source_hashは索引を作った資料の中身のハッシュ(sha256)。is_current(data)で、資料が変わっていないかを
  確かめられる(変わっていれば作り直す)
- 埋め込みは任意。作ったときの埋め込みのモデル名を持ち、別のモデルの問いと比べないようにする。
  ベクトルは長さ1にそろえて持つ(内積=コサイン類似度)
- 保存先は使う側がパスで渡す。形式はnumpyのnpz(1ファイル。断片等はJSON、ベクトルは配列)で、
  読み込みにpickleを使わない
"""

import hashlib
import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Optional, Union

import numpy as np

from ..generator import EmbeddingGenerator
from .chunk import Chunk

FORMAT_VERSION = 1


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalized(vectors: Union[list[list[float]], np.ndarray]) -> np.ndarray:
    """各行を長さ1にする(長さ0の行はそのまま)。"""
    array = np.asarray(vectors, dtype=np.float32)
    if array.ndim != 2:
        raise ValueError("埋め込みは2次元(断片の数×次元)である必要があります。")
    norms = np.linalg.norm(array, axis=1, keepdims=True)
    return array / np.where(norms == 0, 1, norms)


@dataclass
class ChunkIndex:
    source: str
    chunks: list[Chunk]
    source_hash: str = ""
    embedding_model: Optional[str] = None
    vectors: Optional[np.ndarray] = field(default=None, repr=False)  # (断片の数, 次元)、各行の長さは1

    def __post_init__(self) -> None:
        if (self.vectors is None) != (self.embedding_model is None):
            raise ValueError("埋め込みのベクトルとモデル名は、両方あるか両方無いかのどちらかです。")
        if self.vectors is not None and len(self.vectors) != len(self.chunks):
            raise ValueError("埋め込みの数が断片の数と合いません。")

    @property
    def has_embeddings(self) -> bool:
        return self.vectors is not None

    def is_current(self, data: bytes) -> bool:
        """dataが、この索引を作った資料と同じ中身か。"""
        return bool(self.source_hash) and self.source_hash == content_hash(data)

    def with_embeddings(self, embedder: EmbeddingGenerator) -> "ChunkIndex":
        """断片を埋め込んだ索引を返す(自身は変えない)。"""
        vectors = embedder.embed([c.text for c in self.chunks], "document") if self.chunks else []
        array = normalized(vectors) if self.chunks else np.zeros((0, 0), dtype=np.float32)
        return replace(self, embedding_model=embedder.model_name, vectors=array)

    def save(self, path: Union[str, Path]) -> None:
        meta = {
            "format_version": FORMAT_VERSION,
            "source": self.source,
            "source_hash": self.source_hash,
            "embedding_model": self.embedding_model,
            "chunks": [
                {"chunk_id": c.chunk_id, "text": c.text, "kind": c.kind, "locator": c.locator} for c in self.chunks
            ],
        }
        vectors = self.vectors if self.vectors is not None else np.zeros((0, 0), dtype=np.float32)
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:  # np.savezにパスを渡すと拡張子.npzが付け足されるため、ファイルで渡す
            np.savez_compressed(f, meta=np.array(json.dumps(meta, ensure_ascii=False)), vectors=vectors)

    @classmethod
    def load(cls, path: Union[str, Path]) -> "ChunkIndex":
        with np.load(path, allow_pickle=False) as archive:
            meta = json.loads(str(archive["meta"]))
            vectors = archive["vectors"]
        if meta.get("format_version") != FORMAT_VERSION:
            raise ValueError(f"索引の形式の版が違います({meta.get('format_version')})。作り直してください。")
        source = meta["source"]
        chunks = [Chunk(source=source, **c) for c in meta["chunks"]]
        model = meta.get("embedding_model")
        return cls(
            source=source,
            chunks=chunks,
            source_hash=meta.get("source_hash", ""),
            embedding_model=model,
            vectors=vectors if model is not None else None,
        )
