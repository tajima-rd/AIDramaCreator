# tests/api/test_dataset_file.py
"""
PDF等のファイルをDatasetとして追加する(routers/dataset.py)の結合テスト。

- PDFを追加すると、ドラマ未割当・dataset_category=reference・file_format=pdfで一覧に出ること
- サイドカーのデータメタデータYAMLが作られ、列は空であること
- ファイルそのものをPDFとして(inlineで)取得でき、CSVの中身の取得は400であること
- DOCX・XLSX(参考資料)も追加でき、ブラウザで表示できないためダウンロード(attachment)で返ること
- 追加できない形式・拡張子と違う中身(ZIPだがWord本体が無い等)・壊れたbase64・大きすぎるファイルは
  400で、何も保存しないこと
"""

import base64
import io
import zipfile

from core.service.api import dataset as dataset_api
from tests.conftest import parse_yaml

TINY_PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def _zip(*members):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name in members:
            archive.writestr(name, "<x/>")
    return buffer.getvalue()


def _upload(client, project, filename, data, **extra):
    body = {"filename": filename, "content_base64": base64.b64encode(data).decode("ascii"), **extra}
    return client.post(f"/projects/{project.project_id}/datasets/files", json=body)


def test_upload_pdf_unassigned(client, project):
    data = TINY_PDF
    resp = _upload(client, project, "CE_analysis.pdf", data)
    assert resp.status_code == 200, resp.text
    summary = parse_yaml(resp)
    assert summary["filename"] == "CE_analysis.pdf"
    assert summary["file_format"] == "pdf"
    assert summary["dataset_category"] == "reference"
    assert summary["drama_id"] is None
    assert summary["size_bytes"] == len(data)

    listed = parse_yaml(client.get(f"/projects/{project.project_id}/datasets"))["datasets"]
    assert [d["file_id"] for d in listed] == [summary["file_id"]]  # サイドカーYAMLは別のDatasetとして数えない

    metadata = parse_yaml(client.get(f"/projects/{project.project_id}/datasets/{summary['file_id']}/metadata"))
    assert metadata["dataset"]["dataset_category"] == "reference"
    assert metadata["columns"] == []
    assert metadata["provenance"]["process"] == "manually_registered"

    resp = client.get(f"/projects/{project.project_id}/datasets/{summary['file_id']}/file")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.headers["content-disposition"].startswith("inline")
    assert resp.content == data

    resp = client.get(f"/projects/{project.project_id}/datasets/{summary['file_id']}")
    assert resp.status_code == 400  # CSVの中身としては読めない


def test_upload_docx_and_xlsx(client, project):
    docx = _zip("[Content_Types].xml", "word/document.xml")
    xlsx = _zip("[Content_Types].xml", "xl/workbook.xml")
    for filename, data, fmt in (("supplement.docx", docx, "docx"), ("inputs.xlsx", xlsx, "xlsx")):
        resp = _upload(client, project, filename, data)
        assert resp.status_code == 200, resp.text
        summary = parse_yaml(resp)
        assert (summary["file_format"], summary["dataset_category"]) == (fmt, "reference")
        resp = client.get(f"/projects/{project.project_id}/datasets/{summary['file_id']}/file")
        assert resp.content == data
        assert resp.headers["content-disposition"].startswith("attachment")
    assert resp.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_upload_rejects_invalid_files(client, project, monkeypatch):
    assert _upload(client, project, "notes.txt", b"hello").status_code == 400  # 追加できない形式
    assert _upload(client, project, "fake.pdf", b"not a pdf").status_code == 400  # 中身がPDFでない
    assert _upload(client, project, "fake.docx", _zip("xl/workbook.xml")).status_code == 400  # Word本体が無い
    assert _upload(client, project, "fake.xlsx", TINY_PDF).status_code == 400  # ZIPでない
    resp = client.post(
        f"/projects/{project.project_id}/datasets/files",
        json={"filename": "broken.pdf", "content_base64": "!!!not base64!!!"},
    )
    assert resp.status_code == 400
    monkeypatch.setattr(dataset_api, "MAX_UPLOAD_BYTES", 10)
    assert _upload(client, project, "big.pdf", TINY_PDF).status_code == 400  # 大きすぎる
    assert parse_yaml(client.get(f"/projects/{project.project_id}/datasets"))["datasets"] == []
