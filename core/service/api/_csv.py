# core/service/api/_csv.py
"""
CSVを文字列で受け取るAPI(schemaの型はCSVを文字列で運ぶ)のうち、処理側(core.service.
process)がファイルパスを要求するものに、一時ファイルとして渡すための内部ヘルパー。
"""

import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager


@contextmanager
def csv_temp_file(csv_text: str, filename: str = "data.csv") -> Iterator[str]:
    """csv_textを一時ディレクトリへ書き出し、そのパスを渡す(ブロックを抜けると削除する)。"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        csv_path = os.path.join(tmp_dir, filename)
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write(csv_text)
        yield csv_path
