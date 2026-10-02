"""
core.gisは他のプロジェクトでも使えるよう、パッケージの外をimportしないこと(core.genaiと同じ)。
場所(Location)・移動(SiteFlow)等のAIDCの意味づけは、使う側(core.infra・core.service)が持つ。

- パッケージの中どうしは相対import(from .x / from ..x)だけを使い、core.*(core.gis自身を含む)・
  api・cli・appsを絶対importしないこと
"""

import ast
from pathlib import Path

import core.gis

GIS_DIR = Path(core.gis.__file__).parent
APP_PACKAGES = ("core", "api", "cli", "apps", "tests")


def _absolute_imports(path: Path) -> list[str]:
    names = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.append(node.module)
    return names


def test_gis_does_not_import_outside_itself():
    violations = [
        f"{path.relative_to(GIS_DIR)}: {name}"
        for path in sorted(GIS_DIR.rglob("*.py"))
        for name in _absolute_imports(path)
        if name.split(".")[0] in APP_PACKAGES
    ]
    assert violations == []
