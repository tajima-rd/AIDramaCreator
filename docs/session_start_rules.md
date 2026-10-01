# 新しいセッションで最初にやること

## 1. 読む順番

1. [overview.md](overview.md) — 目的・制作の流れ
2. [architecture.md](architecture.md) — 確定済みの設計判断・落とし穴
3. [status.md](status.md) — 実装済みの範囲
4. [open_tasks.md](open_tasks.md) — 残タスク
5. [known_issues.md](known_issues.md) — 既知のバグ・技術的負債
6. [future_design.md](future_design.md) — 未決定の構想(該当する作業では、実装前にユーザーに確認する)
7. [model_design.md](model_design.md) — `core/model/`(作品・エージェント)の設計
8. [database_design.md](database_design.md) — 作品モデルのDB(正本・版・下書き)
9. [qidm_reuse.md](qidm_reuse.md) — QIDMから再利用できるもの(新しく作る前に、ここに無いか確かめる)

## 2. 心構え

- 別プロジェクト(QIDM)から持ち込んだコード・記述が残っている。docstringやコメントに書かれたQIDMの概念
  (Domain・Run・domain.db等)を、AIDCの設計として扱わないこと。
- 不明な点は推測せず、ユーザーに質問する。

## 3. コードの読み方

- 制作の流れの入口は`main.py`→`core/service/process/production/`→`core/prompt/drama_production/`。
- APIキーは`~/.aidc/secrets.env`の`AIDC_GEMINI_API_KEY`から読む(`main.py`→`generator_builder.saved_api_key`)。
  シェルの環境変数からは読まない。保存は公開APIの`preference`か`core.infra.store.secret_env_store.save_secret`。
- 生成AIは`core/genai/__init__.py`のdocstringに全体の案内がある。

## 4. 動作確認

- Python 3.12、`.venv`を使う(`.venv/bin/python main.py Project/TEST_PROJECT_01`。使い方は`main.py`のdocstring)。
  音声の連結にffmpegが必要。
- 生成AIを呼ぶ工程はAPIキーと課金を伴う。実行の前にユーザーに確認すること。
- 自動テスト: `.venv/bin/python -m pytest`(依存は`requirements/dev.txt`)。テストはtmp_pathの
  中だけで動き、実レジストリ(`~/.aidc/`)に触れない。
- 動かすときは`apps/sample_data/`を`Project/TEST_PROJECT_##`(01からの連番)へ複製して使う([architecture.md](architecture.md) 5節。`drama/`・`agent/`を`model/`に、`project.yaml`を直下に)。`Project/`はgitの管理外。

## 5. 秘密情報

- APIキーをリポジトリ・コード・ログに書かない。`.secret`はgitの管理外(中身を読まない・出力しない)。

## 6. 作業完了後のドキュメント更新

- 新機能 → [status.md](status.md)
- 設計判断 → [architecture.md](architecture.md)(決まった項目は [future_design.md](future_design.md) から消す)
- バグの発見 → [known_issues.md](known_issues.md)、バグの解消 → known_issues.mdから完全に削除する
- タスクの追加・完了 → [open_tasks.md](open_tasks.md)
