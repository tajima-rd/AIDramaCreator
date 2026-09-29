# core/genai/rag/chunk.py
"""
資料の構成要素の型。

- Block: 資料から取り出したひとまとまり(PDFの1ページ・DOCXの1段落/1つの表・XLSXの1シート等)。
  locatorは資料の中の場所を人が読める形で表したもの("page 3"・"table 2"・"sheet Inputs")で、
  生成AIが根拠の場所を示すときにそのまま使える
- Chunk: 検索の単位。Blockを検索に向いた長さに分けたり、短いものをまとめたりしたもの
"""

from dataclasses import dataclass
from typing import Literal

BlockKind = Literal["text", "table"]


@dataclass(frozen=True)
class Block:
    text: str
    kind: BlockKind
    locator: str
    # 表の直前の短い段落(表の題。「Table 3. ...」等)。表を分けても各断片に付けて、題で探せるようにする
    caption: str = ""


@dataclass(frozen=True)
class Chunk:
    chunk_id: str  # 資料の中で一意("<source>#<番号>")
    source: str  # 資料の名前(ファイル名等、使う側が決める)
    text: str
    kind: BlockKind
    locator: str

    @property
    def label(self) -> str:
        """資料の名前と場所("paper.pdf page 3")。文脈の見出しや根拠の表示に使う。"""
        return f"{self.source} {self.locator}".strip()
