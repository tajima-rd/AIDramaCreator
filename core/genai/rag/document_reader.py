# core/genai/rag/document_reader.py
"""
資料(PDF・DOCX・XLSX・CSV)から、生成AIに渡すテキストを場所付きのBlockの列として取り出す。

生成AIがPDFを直接読めない場合(手元のLLM等)や、DOCX・XLSXのように直接読める提供元が無い形式で使い、
検索(rag)の入力にもなる。生成AIが根拠の場所を示せるよう、PDFはページごと、DOCXは段落と表を文書の
順に並べ、表はMarkdownの表にする(資料の数値は表にあることが多いため、表の構造を崩さない)。XLSXは
シートごとの表、CSVは1つの表。

- document_blocks: 場所付きのBlockの列(検索の分割に使う)
- document_text: 資料全体を1つのテキストにしたもの(資料を丸ごと渡す場合)。PDFは「[page N]」、
  XLSXは「[sheet 名前]」を付ける

形式(file_format)は拡張子に対応する"pdf"・"docx"・"xlsx"・"csv"。PDFにはpypdfが必要。
"""

import csv
import io
import re
import zipfile
from xml.etree import ElementTree

from .chunk import Block

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
S_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

# 表の直前の段落を表の題とみなす長さの上限(これより長い段落は本文とみなす)
CAPTION_MAX_CHARS = 300


def markdown_table(rows: list[list[str]]) -> str:
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [[c.replace("|", "\\|").replace("\n", " ").strip() for c in r] + [""] * (width - len(r)) for r in rows]
    lines = ["| " + " | ".join(rows[0]) + " |", "| " + " | ".join(["---"] * width) + " |"]
    lines += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(lines)


def pdf_blocks(data: bytes) -> list[Block]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return [
        Block((page.extract_text() or "").strip(), "text", f"page {number}")
        for number, page in enumerate(reader.pages, start=1)
    ]


def _docx_paragraph_text(paragraph: ElementTree.Element) -> str:
    return "".join(t.text or "" for t in paragraph.iter(f"{W_NS}t"))


def docx_blocks(data: bytes) -> list[Block]:
    """段落と表を文書の順に並べる(表はMarkdownの表。セル内の複数段落は空白でつなぐ)。"""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    body = root.find(f"{W_NS}body")
    blocks: list[Block] = []
    paragraphs = tables = 0
    for element in body if body is not None else []:
        if element.tag == f"{W_NS}p":
            text = _docx_paragraph_text(element).strip()
            if text:
                paragraphs += 1
                blocks.append(Block(text, "text", f"paragraph {paragraphs}"))
        elif element.tag == f"{W_NS}tbl":
            rows = []
            for row in element.iter(f"{W_NS}tr"):
                cells = []
                for cell in row.findall(f"{W_NS}tc"):
                    cells.append(" ".join(_docx_paragraph_text(p).strip() for p in cell.findall(f"{W_NS}p")).strip())
                rows.append(cells)
            table = markdown_table(rows)
            if table:
                tables += 1
                previous = blocks[-1] if blocks else None
                caption = (
                    previous.text
                    if previous is not None and previous.kind == "text" and len(previous.text) <= CAPTION_MAX_CHARS
                    else ""
                )
                blocks.append(Block(table, "table", f"table {tables}", caption))
    return blocks


def _column_index(cell_ref: str) -> int:
    letters = re.match(r"[A-Z]+", cell_ref or "A")
    index = 0
    for ch in letters.group(0) if letters else "A":
        index = index * 26 + (ord(ch) - ord("A") + 1)
    return index - 1


def xlsx_blocks(data: bytes) -> list[Block]:
    """シートごとにMarkdownの表にする(式は計算済みの値、共有文字列は文字列に戻す)。"""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = set(archive.namelist())
        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            for item in ElementTree.fromstring(archive.read("xl/sharedStrings.xml")).iter(f"{S_NS}si"):
                shared.append("".join(t.text or "" for t in item.iter(f"{S_NS}t")))
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        rels = {}
        if "xl/_rels/workbook.xml.rels" in names:
            for rel in ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels")):
                rels[rel.get("Id")] = rel.get("Target")
        blocks = []
        for sheet in workbook.iter(f"{S_NS}sheet"):
            target = rels.get(sheet.get(f"{R_NS}id"), "")
            path = "xl/" + target.lstrip("/").removeprefix("xl/") if target else ""
            if path not in names:
                continue
            rows = []
            for row in ElementTree.fromstring(archive.read(path)).iter(f"{S_NS}row"):
                cells: dict[int, str] = {}
                for cell in row.findall(f"{S_NS}c"):
                    value = cell.find(f"{S_NS}v")
                    text = value.text if value is not None and value.text is not None else ""
                    if cell.get("t") == "s" and text:
                        text = shared[int(text)]
                    elif cell.get("t") == "inlineStr":
                        text = "".join(t.text or "" for t in cell.iter(f"{S_NS}t"))
                    cells[_column_index(cell.get("r"))] = text
                if cells:
                    rows.append([cells.get(i, "") for i in range(max(cells) + 1)])
            blocks.append(Block(markdown_table(rows), "table", f"sheet {sheet.get('name')}"))
    return blocks


def csv_blocks(data: bytes) -> list[Block]:
    text = data.decode("utf-8-sig", errors="replace")
    return [Block(markdown_table(list(csv.reader(io.StringIO(text)))), "table", "table")]


READERS = {"pdf": pdf_blocks, "docx": docx_blocks, "xlsx": xlsx_blocks, "csv": csv_blocks}
# 資料全体のテキストで、Blockの前に場所(「[page N]」等)を付ける形式
LABELED_FORMATS = ("pdf", "xlsx")


def document_blocks(data: bytes, file_format: str) -> list[Block]:
    """file_formatに応じてBlockの列を取り出す。未対応の形式はValueError。"""
    reader = READERS.get(file_format)
    if reader is None:
        raise ValueError(f"この形式からはテキストを取り出せません: {file_format}")
    return reader(data)


def document_text(data: bytes, file_format: str) -> str:
    """資料全体を1つのテキストにする。未対応の形式はValueError。"""
    blocks = document_blocks(data, file_format)
    if file_format in LABELED_FORMATS:
        return "\n\n".join(f"[{b.locator}]\n{b.text}" for b in blocks)
    return "\n\n".join(b.text for b in blocks)
