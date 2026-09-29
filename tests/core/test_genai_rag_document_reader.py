"""
資料からのテキストの取り出し(core.genai.rag.document_reader)。

- PDFはページごとに「[page N]」を付ける(生成AIが根拠のページを示せるように)
- DOCXは段落と表を文書の順に並べ、表はMarkdownの表にする(補足資料の数値の表を崩さない)
- XLSXはシートごとの表(共有文字列を文字列に戻す)、CSVは表
- 未対応の形式はValueError
"""

import io
import os
import zipfile

import pytest

from core.genai.rag.document_reader import document_text
from tests.conftest import REFERENCE_SAMPLE_DIR, requires_reference_samples

THESIS = REFERENCE_SAMPLE_DIR


def _read(name):
    with open(os.path.join(THESIS, name), "rb") as f:  # ゴールデン入力は読むだけ
        return f.read()


@requires_reference_samples
def test_pdf_pages():
    text = document_text(_read("CE_analysis_Nefecon+BSC_vs_BSC.pdf"), "pdf")
    assert text.startswith("[page 1]") and "[page 2]" in text
    assert "semi-Markov" in text


@requires_reference_samples
def test_docx_tables_in_order():
    text = document_text(_read("389456.docx"), "docx")
    caption = text.index("Supplementary Table 3.")
    table = text.index("| CKD stage | Patients at diagnosis (%) |", caption)
    assert caption < table < text.index("Supplementary Table 4.")
    assert "| CKD 1* | 3% |" in text


def test_xlsx_and_csv():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                   '<sheets><sheet name="Inputs" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/sharedStrings.xml", '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                   '<si><t>State</t></si><si><t>Share</t></si><si><t>A</t></si></sst>')
        z.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                   '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>'
                   '<row r="2"><c r="A2" t="s"><v>2</v></c><c r="B2"><v>0.25</v></c></row></sheetData></worksheet>')
    assert document_text(buffer.getvalue(), "xlsx") == "[sheet Inputs]\n| State | Share |\n| --- | --- |\n| A | 0.25 |"
    assert document_text(b"a,b\n1,2\n", "csv") == "| a | b |\n| --- | --- |\n| 1 | 2 |"
    with pytest.raises(ValueError):
        document_text(b"x", "other")
