# QIDMから再利用できるもの

QIDM(`/home/yufujimoto/Git/QuantumInspiredDomainModel`、2026-09-29時点のHEAD `71a4a4d`)のうち、AIDCで再利用できそうなものの一覧。
QIDMは全く別のプロジェクト(量子に着想を得た領域モデル)なので、Domain・Feature・Factor・Association・Simulation等の
**QIDM固有の概念は持ち込まない**。

2026-09-29に、A群とB群は持ち込み済み(GUI・`.claude/skills`は保留していた)。2026-10-01にGUIの枠を`apps/AIDC-Console`へ持ち込んだ(下の「持ち込み済み」)。
持ち込んだ内容は [status.md](status.md)。QIDMのDomainはDramaへ仮に置き換えた([future_design.md](future_design.md))。

「Domain依存」は、そのファイルの中でDomain・Feature等に触れている箇所の数の目安。

## A. ほぼそのまま使える(Domainに依存しない)

| QIDMのパス | 内容 | 持ち込むときの修正 |
| --- | --- | --- |
| `core/genai/` | 生成AIライブラリ | **持ち込み済み**(中身はQIDMと同じ) |
| `core/infra/store/secret_env_store.py` | APIキーの保存・読み込み(`~/.qidm/secrets.env`) | 保存先を`~/.aidc/`に |
| `core/infra/store/project_registry_store.py` | プロジェクトのレジストリ(project_id→ディレクトリ) | 保存先を`~/.aidc/`に |
| `core/infra/store/dataset_file_store.py` | Dataset本体とサイドカーYAMLのファイル操作 | なし |
| `core/service/process/genai/generator_builder.py` | Projectの設定と保存済みのキーから生成器を作る | なし |
| `core/service/process/genai/llm_connection_tester.py`・`embedding_connection_tester.py`・`genai_setting_inspector.py` | 生成AIの接続確認と設定の入力補助 | なし |
| `core/service/process/genai/reference_searcher.py` + `core/prompt/reference_search.py` + `core/schema/formats/reference_language.py` | 参考資料(Dataset)の索引と検索(RAGの組み込み) | Domainへの言及を消す。`reference_language.py`は持ち込み済み |
| `core/service/process/edit/preference_editor.py` | 生成AIの設定(project.yamlの`genai:`)の更新 | なし |
| `core/service/api/project.py`・`preference.py`、`core/schema/api/project.py`・`preference.py`、`api/routers/project.py`・`preference.py` | プロジェクトと設定の公開API・DTO・HTTP | Projectの作り直しに合わせる |
| `api/yaml_io.py`・`api/routers/_http.py` | YAMLでのやり取りと、例外→HTTPステータスの対応 | **持ち込み済み** |
| `requirements/`(base・dev・genai・rag-ja)・`pyproject.toml` | 用途別の依存と、ruff・black・pytestの設定 | 依存をAIDCに合わせて入れ替え |
| `scripts/server/`(start・stop・restart)・`scripts/llamacpp/` | APIサーバー・llama.cppの起動と停止 | 環境変数名(`QIDM_*`)を変更 |
| `tests/core/test_genai_*.py`・`test_character_check.py`・`test_reference_searcher.py`、`tests/api/test_preference.py` | genai・設定のテスト(`test_genai_independence.py`はgenaiの独立性を確かめる) | なし〜小 |
| `apps/QIDM/static/project_genai_tab.js`・`data_viewer_panel.js`・`vendor/js-yaml.min.js` | GUI: 生成AIの設定タブ、Datasetの表示(CSV・PDF) | **持ち込み済み**(`apps/AIDC-Console/static/`、2026-10-01) |
| `.claude/skills/qidm-browser-verify/` | headless ChromeによるGUIの検証 | GUIを作ってから |

## B. Domainへの依存を外せば使える

| QIDMのパス | 内容 | Domain依存 / 外すもの |
| --- | --- | --- |
| `core/project/project.py` | `Project`・`ProjectLayout`・`LlmSetting`/`TtsSetting`/`EmbeddingSetting` | 16。DBファイル名の定数(domain.db等)、`RunNotFoundError`。AIDCにある版は一部だけ |
| `core/project/dataset.py` | `Dataset`・拡張子→形式 | 2。`domain_id`。**持ち込み済み** |
| `core/infra/store/project_file_store.py` | project.yamlの読み書き | 7。DBファイル名・`paths`セクション |
| `core/service/process/edit/project_editor.py` | プロジェクトの作成・更新 | 5 |
| `core/service/process/edit/dataset_editor.py` | Datasetの保存・改名・削除とメタデータYAML | 71。Domainとの紐付け・`dataset_category` |
| `core/infra/store/dataset_registry_store.py` | Datasetの台帳(file_id↔filename) | 29。**QIDMではdomain.dbのテーブル**。AIDCのSQLiteの設計次第 |
| `core/schema/formats/dataset_metadata.py` | データメタデータYAML | Domain関連の項目と`DatasetCategory`の値。**持ち込み済み** |
| `core/service/api/dataset.py`・`core/schema/api/dataset.py`・`api/routers/dataset.py` | Datasetの公開API・DTO・HTTP | 76・15・19 |
| `api/main.py` | FastAPIの生成・routerのinclude・静的ファイル・共通の例外ハンドラ | 29。include・例外の一覧を入れ替える。AIDCにある版はimport文だけ |
| `tests/conftest.py`・`tests/api/test_project.py`・`test_dataset.py`・`test_dataset_file.py` | テストの共通部品とプロジェクト・Datasetのテスト | 7・2・25・12 |
| `apps/QIDM/static/app.js`・`app.css`・`project_overview_panel.js` | GUIの枠(メニュー・Tree・Properties・APIクライアント)とプロジェクトの概要 | **持ち込み済み**(2026-10-01。Domain系・Propertiesの区画・QIDM専用のCSSは除いた) |

## C. 仕組み・設計を参考にする(そのままは使えない)

| QIDMのパス | 参考になる点 |
| --- | --- |
| drafts一式: `core/schema/formats/domain_draft.py`・`core/infra/store/draft_store.py`・`core/service/process/edit/domain_draft_editor.py`・`core/service/process/genai/domain_draft_assistant.py`・`draft_character_checker.py`・`core/prompt/model_building/`・`service/api`・`schema/api`・`routers`の`domain_draft`・`apps/QIDM/static/domain_draft_panel.js` | `drafts/<draft_id>/`に管理情報・作成途中の成果物・根拠・生成AIとの会話・版の履歴を置き、ステップごとに生成AIと対話して提案をApply/Undoする仕組み。プロンプトは「共通の説明(guide)+ステップごとの指示と応答の型(step)」 |
| `core/infra/store/domain_store.py`等のSQLiteのstore | 1DB=1モジュール、`save()`を書き込みの一元的な入口にする、スキーマの作成(`ensure_schema`)、明示的な保存(Save Schema)による版の管理 |
| QIDMの`docs/architecture.md`「coreのパッケージ構成と責務」 | パッケージの役割・依存方向・ファイルの命名規則(A: 定義は単数形の名詞、B: 処理は「対象_役割」、C: 境界はリソース単位で`schema/api`・`service/api`・`api/routers`を1対1)・落とし穴 |
| QIDMの`docs/session_start_rules.md` | 「コードを読む(車輪の再発明をしない)」「実装前の確認事項」「安全に検証するための厳守ルール」の節 |

## 対象外(QIDM固有)

`core/base/`・`core/engine/`・`core/model/`(量子のドメインモデル)、`service/process`の`analysis/`・`simulation/`・`transfer/`と
Domain系の`edit/`、`infra/io/`(モデル定義YAML・エンティティ定義表)、Domain・分析・シミュレーション系の`service/api`・`schema`・`routers`・GUI。
