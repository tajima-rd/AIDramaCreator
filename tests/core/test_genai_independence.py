"""
core.genaiは他のプロジェクトでも使えるよう(将来は独立したリポジトリで管理する)、パッケージの外を
importしないこと。AIDCの設定・APIキーの置き場所との橋渡しは
core.service.process.genai.generator_builderが行う。

- パッケージの中どうしは相対import(from .x / from ..x)だけを使い、core.*(core.genai自身を含む)・
  api・cli・appsを絶対importしないこと
- 生成器はAIDCの型を介さず、提供元の名前・モデル・接続先・APIキーの値だけで作れること
"""

import ast
from pathlib import Path

import pytest

import core.genai
from core.genai import create_text_generator
from core.genai.openai_compatible import OpenAiCompatibleTextGenerator

GENAI_DIR = Path(core.genai.__file__).parent
APP_PACKAGES = ("core", "api", "cli", "apps", "tests")


def _absolute_imports(path: Path) -> list[str]:
    names = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.append(node.module)
    return names


def test_genai_does_not_import_outside_itself():
    violations = [
        f"{path.relative_to(GENAI_DIR)}: {name}"
        for path in sorted(GENAI_DIR.rglob("*.py"))
        for name in _absolute_imports(path)
        if name.split(".")[0] in APP_PACKAGES
    ]
    assert violations == []


def test_create_generator_from_plain_values():
    gen = create_text_generator("LlamaCpp", "qwen", api_url="http://localhost:8080", api_key="k")
    assert isinstance(gen, OpenAiCompatibleTextGenerator)
    assert (
        gen.url == "http://localhost:8080/v1/chat/completions"
        and gen.headers["Authorization"] == "Bearer k"
    )
    with pytest.raises(ValueError):
        create_text_generator("OpenWebUI", "m", api_url="http://localhost:3000")  # キーが必須
    with pytest.raises(ValueError):
        create_text_generator("Ollama", "m")  # URLが必須
