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
| `core/model/` | `drama/`=作られる作品、`agent/`=作品作りに参加する者(クラスと属性のみ。[docs/model_design.md](docs/model_design.md))。純粋なモデルだけを置き、`core.model`の外をimportしない。`identifier.py`はUUIDの識別子(現行の制作の流れが使う旧来の原稿の型は`schema/formats/_legacy_drama.py`。制作の流れを新しいモデルへ移したら消す) |
| `core/default/` | システム既定(`agents/`=エージェントの職能ごとの既定。正本。プロジェクトの作成時に`<プロジェクト>/user_default/`へ複製する) |
| `core/project/` | プロジェクトの定義のみ: `Project`(project.yamlに対応する集約の根)・`ProjectLayout`(構成要素の所在)・`Dataset`。操作は`infra/store`・`service/process`にある(QIDM由来の暫定の形) |
| `core/prompt/` | 用途ごとのプロンプトと、生成AIに返させる構造。生成AIは呼ばない。`drama_production/`=制作の流れの各工程、`reference_search.py`=資料の検索の問い、`character_import.py`=企画書の登場人物の取り込み、`agent_instruction.py`=エージェントの情報から指示の節を組み立てる共通の部品、`ai_build/`=Build with AIの工程(タブ)の対応表と工程ごとのプロンプト |
| `core/genai/` | 生成AIの汎用ライブラリ(文章生成・構造化出力・音声合成・埋め込み・プロンプトの部品・`rag/`=資料の検索)。**他のプロジェクトでも使う独立したライブラリの候補なので、パッケージの外(`core.*`等)をimportしない**(Projectの設定・キーとの橋渡しは`core/service/process/genai/generator_builder.py`) |
| `core/gis/` | 地理情報(GIS)の汎用ライブラリ(`geometry.py`=WKTの検査・正規化とGeoJSONとの変換、`io/`=GeoPackage・KML・KMZの読み書き、`analysis/`=空間の関係)。**`core/genai`と同じく、パッケージの外(`core.*`等)をimportしない**。Location・SiteFlow等の意味づけは使う側(`infra`・`service`)が持つ |
| `core/infra/io/` | 外部とやり取りするファイル形式との変換(`model_definition_*`=モデル定義YAML、`geodata_reader.py`=場所の地図(KML・KMZ・GeoPackage)をLocation・SiteFlow・補助情報の層に分ける。形式の読み書きそのものは`core/gis`) |
| `core/infra/store/` | 内部状態の永続化(`*_store`): project.yaml・プロジェクトのレジストリ(`~/.aidc/projects.yaml`)・APIキー(`~/.aidc/secrets.env`)・Datasetのファイルと台帳(`project.db`)・作品モデルの正本・版・下書き(`project.db`。場所・移動の表を持つGeoPackageとしても読める。[docs/database_design.md](docs/database_design.md)) |
| `core/service/process/` | 内部の処理(フォルダは分野、ファイル名は「対象_役割」): `production/`=制作の流れの各工程、`edit/`=プロジェクト・設定・Datasetの手順、`genai/`=生成AIを使う処理 |
| `core/service/api/` | システムの公開API。識別子(project_id・file_id)とschemaの型でやり取りし、`schema/api`・`api/routers`と同名のリソース単位(`project`・`preference`・`dataset`・`drama_model`・`drama_draft`・`agent_default`・`character_import`・`ai_build`・`voice`)で構成する |
| `core/schema/` | 契約(pydantic)。`api/`=公開APIのDTO、`formats/`=ディスクに残るファイル形式 |
| `api/` | インターフェース: HTTP(FastAPI、要`requirements/api.txt`)。`main.py`はinclude_routerと共通の例外ハンドラ(Project/Datasetの不在→404)のみ、`routers/`はHTTPとschemaを橋渡しするだけ |
| `apps/AIDC-Console/` | インターフェース: Web GUI(素のHTML/CSS/JS。APIサーバーが`/app/`で配信。[docs/architecture.md](docs/architecture.md) 8節) |
| `apps/sample_data/` | サンプルの作品・エージェントの、分割方式のモデル定義YAML。作品ごとのディレクトリ(`令和但馬道中膝栗毛/`・`ハチ北スキー場ガイド/`)の下に`drama/`=作品、`agent/`=エージェント。直下の`project.yaml`=プロジェクトの見本。`ハチ北スキー場ガイド/ハチ北スキー場.kml`=場所の雛形(`apps/AIDC-Console/templates/`)の形の地図。`main.py`で使うときは作品のディレクトリの`drama/`・`agent/`を`Project/TEST_PROJECT_##/model/`に、`project.yaml`をその直下に複製する |
| `tests/` | pytest(`api/`=結合テスト、`core/`=コアのテスト。要`pip install -r requirements/dev.txt`) |
| `requirements/` | 依存(`base`=本体、`api`=HTTP、`dev`=開発用、`rag-ja`=日本語の形態素解析) |
| `scripts/` | 起動・停止のシェルスクリプト(`server/`=APIサーバー、`llamacpp/`=手元のLLMサーバー) |
| `docs/` | 設計ドキュメント一式 |

## 厳守ルール(必ず確認すること)

- **実験用のプロジェクトは`Project/TEST_PROJECT_##`(リポジトリ直下、`##`は01からの連番)に作る。** 中身は
  `apps/sample_data/`の複製から始める(`apps/sample_data/`を直接`root_dir`にしない。`main.py`も断る)。
  `Project/`はgitの管理外(`.gitignore`)。
- **旧来の形(テキストのファイルのプロジェクト等)との互換性は考えない**(2026-10-01ユーザー)。移行が済んだものは、
  設計も含めて残さない。
- APIキーをリポジトリ・コード・ログに書かない。
- テストはユーザーの実レジストリ(`~/.aidc/`)に触れない(`tests/conftest.py`の`isolated_registry`)。

## 作業完了後

該当する変更を`docs/`に反映すること(新機能→status.md、設計判断→architecture.md、
バグ発見→known_issues.md、バグ解消→known_issues.mdから完全削除)。詳細は
[docs/session_start_rules.md](docs/session_start_rules.md) 6節。
