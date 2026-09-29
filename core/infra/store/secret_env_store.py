# core/infra/store/secret_env_store.py
"""
生成AIのAPIキーの保存・読み込み(Project > Preferencesで入力したキー)。

- AIDCが使うAPIキーは、ここに保存したものだけ。シェルの環境変数(~/.bashrc等)からは読まず、
  プロセスの環境変数(os.environ)にも入れない(2026-09-28ユーザー決定)
- キーの名前はシステムが提供元と接続先から決める(core.service.process.genai.generator_builder.api_key_name、
  例: AIDC_GEMINI_API_KEY、AIDC_LLAMACPP_LOCALHOST_8080_API_KEY)。保存できるのはこの形の名前だけ
- 保存先はリポジトリ・プロジェクトの外の、利用者のホームディレクトリ(既定は
  ~/.aidc/secrets.env、AIDC_SECRETS_PATHで変更可)。.env形式(NAME='value')で、所有者だけが
  読み書きできる権限(600)にする。リポジトリの.gitignoreにもsecrets.envを入れてある

テストはSECRETS_PATHをtmp_path配下へ差し替えて、利用者の実ファイルに触れないようにする
(tests/conftest.py)。
"""

import os
import re

from dotenv import dotenv_values, set_key

SECRETS_PATH = os.environ.get(
    "AIDC_SECRETS_PATH",
    os.path.join(os.path.expanduser("~"), ".aidc", "secrets.env"),
)

SECRET_NAME_PATTERN = re.compile(r"^AIDC_[A-Z0-9_]+_API_KEY$")


def validate_secret_name(name: str) -> None:
    """保存してよい名前か(AIDC_…_API_KEY)。違えばValueError。"""
    if not SECRET_NAME_PATTERN.match(name or ""):
        raise ValueError(f"APIキーの名前が不正です: {name}")


def load_saved() -> dict[str, str]:
    """保存済みのAPIキー(名前 → 値)。ファイルが無ければ空。"""
    if not os.path.exists(SECRETS_PATH):
        return {}
    return {k: v for k, v in dotenv_values(SECRETS_PATH).items() if v}


def get_secret(name: str) -> str | None:
    return load_saved().get(name)


def save_secret(name: str, value: str) -> None:
    """APIキーを保存する(同じ名前があれば置き換える)。"""
    validate_secret_name(name)
    value = (value or "").strip()
    if not value:
        raise ValueError("APIキーを入力してください。")
    if any(c in value for c in "\r\n"):
        raise ValueError("APIキーに改行は使えません。")

    os.makedirs(os.path.dirname(SECRETS_PATH), exist_ok=True)
    if not os.path.exists(SECRETS_PATH):
        # 最初から所有者だけが読み書きできる権限で作る(書いた後にchmodする間の隙を作らない)
        os.close(os.open(SECRETS_PATH, os.O_WRONLY | os.O_CREAT, 0o600))
    set_key(SECRETS_PATH, name, value, quote_mode="always")
    os.chmod(SECRETS_PATH, 0o600)
