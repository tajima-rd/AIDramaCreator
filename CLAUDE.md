# AIDramaCreator (AIDC)

生成AIを使って、だれでも簡単に音声ドラマ風のコンテンツを作るためのシステム。現状はローカルで実行し、
将来はWebアプリにする(API方式)。概要は[docs/overview.md](docs/overview.md)。

## 新しいセッションで最初にやること

**[docs/session_start_rules.md](docs/session_start_rules.md) を読む。** 過去の設計協議の
再現を避けるための読む順番(overview→architecture→status→open_tasks→known_issues→future_design)、
コードの読み方、動作確認手順、作業完了後のドキュメント更新ルールがまとまっている。

着手する機能に応じて、以下も先に確認すること:

- [docs/architecture.md](docs/architecture.md) — 確定済みの設計判断・落とし穴(ADR的位置づけ)
- [docs/status.md](docs/status.md) — 実装済み範囲
- [docs/open_tasks.md](docs/open_tasks.md) — 残タスク
- [docs/known_issues.md](docs/known_issues.md) — 既知バグ・技術的負債
- [docs/future_design.md](docs/future_design.md) — 設計協議が必要な未決定の構想(該当する場合は実装前にユーザーに確認)

## ディレクトリ構成

構成・依存方向・命名規則は別プロジェクトQIDMに合わせている([docs/architecture.md](docs/architecture.md) 1.1)。

| パス | 役割 |
| --- | --- |
| `main.py` | 現行の制作の流れ(あらすじ → 台詞 → 原稿 → 音声)をローカルで実行するスクリプト |
| `core/` | **システム**(インターフェース非依存) |
| `core/model/` | `drama/`=作られる作品、`agent/`=作品作りに参加する者(クラスと属性のみ。[docs/model_design.md](docs/model_design.md))。純粋なモデルだけを置き、`core.model`の外をimportしない。`identifier.py`はUUIDの識別子(現行の制作の流れが使う旧モデルは`schema/formats/_legacy_drama.py`・`service/process/production/_legacy_project.py`) |
| `core/project/` | プロジェクトの定義のみ: `Project`(project.yamlに対応する集約の根)・`ProjectLayout`(構成要素の所在)・`Dataset`。操作は`infra/store`・`service/process`にある(QIDM由来の暫定の形) |
| `core/prompt/` | 用途ごとのプロンプトと、生成AIに返させる構造。生成AIは呼ばない。`drama_production/`=制作の流れの各工程、`reference_search.py`=資料の検索の問い |
| `core/genai/` | 生成AIの汎用ライブラリ(文章生成・構造化出力・音声合成・埋め込み・プロンプトの部品・`rag/`=資料の検索)。**他のプロジェクトでも使う独立したライブラリの候補なので、パッケージの外(`core.*`等)をimportしない**(Projectの設定・キーとの橋渡しは`core/service/process/genai/generator_builder.py`) |
| `core/infra/io/` | 外部とやり取りするファイル形式との変換(`model_definition_*`=モデル定義YAML) |
| `core/infra/store/` | 内部状態の永続化(`*_store`): project.yaml・プロジェクトのレジストリ(`~/.aidc/projects.yaml`)・APIキー(`~/.aidc/secrets.env`)・Datasetのファイルと台帳(`project.db`) |
| `core/service/process/` | 内部の処理(フォルダは分野、ファイル名は「対象_役割」): `production/`=制作の流れの各工程、`edit/`=プロジェクト・設定・Datasetの手順、`genai/`=生成AIを使う処理 |
| `core/service/api/` | システムの公開API。識別子(project_id・file_id)とschemaの型でやり取りし、`schema/api`・`api/routers`と同名のリソース単位(`project`・`preference`・`dataset`)で構成する |
| `core/schema/` | 契約(pydantic)。`api/`=公開APIのDTO、`formats/`=ディスクに残るファイル形式 |
| `api/` | インターフェース: HTTP(FastAPI、要`requirements/api.txt`)。`main.py`はinclude_routerと共通の例外ハンドラ(Project/Datasetの不在→404)のみ、`routers/`はHTTPとschemaを橋渡しするだけ |
| `apps/sample_project/` | サンプルのプロジェクト。ゴールデンで読み取り専用(厳守ルール参照) |
| `apps/sample_data/` | `apps/sample_project/`の人物・プロット・配役を、分割方式のモデル定義YAMLに変換したもの。`main.py`で使うときは`Project/TEST_PROJECT_##/model/`に複製する |
| `tests/` | pytest(`api/`=結合テスト、`core/`=コアのテスト。要`pip install -r requirements/dev.txt`) |
| `requirements/` | 依存(`base`=本体、`api`=HTTP、`dev`=開発用、`rag-ja`=日本語の形態素解析) |
| `scripts/` | 起動・停止のシェルスクリプト(`server/`=APIサーバー、`llamacpp/`=手元のLLMサーバー) |
| `docs/` | 設計ドキュメント一式 |

## 厳守ルール(必ず確認すること)

- **`apps/sample_project/`はゴールデン(正解の見本)で、読み取り専用。** ファイルの追加・変更・削除をしない。
  生成の出力先にも、`Project`の`root_dir`にもしない(`Project`は存在しないディレクトリを作る)。使うときは
  複製してから。例外は、ユーザーが特別に指示した場合だけ。
- **実験用のプロジェクトは`Project/TEST_PROJECT_##`(リポジトリ直下、`##`は01からの連番)に作る。** 中身は
  `apps/sample_project/`の複製から始める。`Project/`はgitの管理外(`.gitignore`)。
- APIキーをリポジトリ・コード・ログに書かない。
- テストはユーザーの実レジストリ(`~/.aidc/`)に触れない(`tests/conftest.py`の`isolated_registry`)。

## 作業完了後

該当する変更を`docs/`に反映すること(新機能→status.md、設計判断→architecture.md、
バグ発見→known_issues.md、バグ解消→known_issues.mdから完全削除)。詳細は
[docs/session_start_rules.md](docs/session_start_rules.md) 6節。
