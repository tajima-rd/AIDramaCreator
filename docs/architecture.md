# アーキテクチャ(確定済みの設計判断)

ここには**確定した**設計判断と落とし穴だけを書く。未決定の構想は [future_design.md](future_design.md)。

## 1. API方式

- 将来のWebアプリ化に備え、システム(`core/`)はインターフェースに依存しない。
  どのインターフェースも、`core/` の公開APIを通して機能を使う。
- 公開APIの形(識別子・DTO・リソースの単位)とインターフェースの実装は未決定([future_design.md](future_design.md))。

## 1.1 基本的な構成はQIDMに寄せる(2026-09-29ユーザー決定)

- `core/`のパッケージ構成は、別プロジェクトQIDMの構成に寄せる。持ち込んだQIDMの骨組み
  (`core/project/`・`core/schema/`・`core/service/`・`core/infra/`・`api/`)は、これから中身が入るので維持する。
- **`service/api`と`service/process`の2層を維持する。**
  - `service/api`: 公開API。
  - `service/process`: 内部の処理。
- 再利用できるQIDMの部品は [qidm_reuse.md](qidm_reuse.md)。ただし、QIDM固有の概念(Domain等)は持ち込まない。

### パッケージ構成

| パッケージ | グループ | 役割 |
| --- | --- | --- |
| `model/` | A | ドラマを構成するオブジェクト |
| `project/` | A | プロジェクトの定義のみ(操作は`infra/store`・`service/process`) |
| `prompt/` | A | 用途ごとのプロンプトと、生成AIに返させる構造。生成AIは呼ばない。`drama_production/`=制作の流れの各工程 |
| `genai/` | (独立) | 生成AIの汎用ライブラリ(2節) |
| `infra/io/`・`infra/store/` | B | 外部とやり取りする形式との変換(現状は空)・内部状態の永続化(`*_store`) |
| `service/process/` | B | 内部の処理。`production/`=制作の流れの各工程(`dialogue_generator`・`scene_generator`・`sound_generator`)、`edit/`=プロジェクト・設定・Datasetの手順、`genai/`=生成AIを使う処理 |
| `service/api/` | C | 公開API(`project`・`preference`・`dataset`) |
| `schema/` | C | 契約(pydantic)。`api/`=公開APIのDTO、`formats/`=ディスクに残るファイル形式 |
| `api/`(core外) | C | インターフェース: HTTP |

### 依存方向(2026-09-29ユーザー決定、QIDMに合わせる)

- インターフェース(`api`等)→`service/api`→`service/process`→`infra`→A(`model`・`project`)の一方向。
  `schema`は契約・ファイル形式の型として各層から参照される。
- A(`model`・`project`)は`infra`・`service`・`schema`・`genai`をimportしない。`infra`は`service`を、
  `service/process`は`service/api`をimportしない。
- `prompt`は`genai.prompt`(プロンプトの部品)と`model`だけを使う。
- `genai`はパッケージの外を一切importしない。生成AIを呼ぶのは`service/process`。

### ファイルの命名規則(2026-09-29ユーザー決定、QIDMに合わせる)

- **A. 静的な状態の定義**(`model`・`project`・`prompt`): 定義する概念の単数形の名詞。役割の接尾辞は付けない。1ファイルに1系統の定義。
- **B. 動的な処理**(`infra/io`・`infra/store`・`service/process`): 「対象_役割」(例: `dialogue_generator`)。
  フォルダ名は役割ではなく処理の分野。
- **C. 外部との境界**(`schema`・`service/api`・`api`): `schema/api`・`service/api`・`api/routers`は同じリソース単位の
  単数形の名詞で1対1に対応させる。
- **共通**: 英小文字のsnake_case。内部専用のモジュールは先頭に`_`。パッケージは現在の規模ではなく、長期的な責務の境界で切る
  (1ファイルだけのパッケージでもよい)。

## 2. 生成AIライブラリ(`core/genai/`)は独立させる

- 他のプロジェクトでも使う独立したライブラリの候補なので、パッケージの外(`core.*`等)をimportしない。
  どの設定・APIキーを使うかは使う側が決め、値として`factory`に渡す。
- 抽象の契約は`generator.py`(`TextGenerator`・`SpeechGenerator`・`EmbeddingGenerator`)。
  具象は`gemini/`・`openai_compatible/`(llama.cpp・Ollama・Open WebUI)。提供元の違いは`factory.py`に集める。
- 提供元の具象は任意の依存(google-genai等)を必要とするため、使うときに初めてimportする。
- 音声合成は現状Geminiのみ(`SPEECH_CLIENTS`)。

## 3. APIキー

- **リポジトリにキーを置かない。** コードへの直書き・project側の設定ファイルへの保存もしない。
- キーは利用者のホームの`~/.aidc/secrets.env`(`AIDC_SECRETS_PATH`で変更可)に保存し、そこからだけ読む。シェルの
  環境変数(`GEMINI_API_KEY`等)からは読まない。制作の流れ(`main.py`)もこの方式に移した(2026-09-29ユーザー決定)。
  キーの名前は提供元と接続先から決まる(`generator_builder.api_key_name`。例: `AIDC_GEMINI_API_KEY`)。

## 4. ドラマを構成するオブジェクトは`core/model/`に置く

- 人物・声・場面・台詞・演出等のドラマの構成要素は`core/model/`に定義する(現状の定義は再定義する予定)。

## 5. `apps/sample_project/`はゴールデン(2026-09-29ユーザー決定)

- リポジトリに含める。中身はゴールデン(正解の見本)で、**読み取り専用**。例外は、ユーザーが特別に指示した場合だけ。
- 現行の`Project`(`core/model/project.py`)は、存在しないディレクトリを作り、生成の結果を書き込む。そのため、
  `apps/sample_project/`を直接`root_dir`にしないこと。使うときは複製してから。
- 実験用のプロジェクトは`Project/TEST_PROJECT_##`(リポジトリ直下、`##`は01からの連番)に、`apps/sample_project/`を
  複製して作る。`Project/`はgitの管理外(`.gitignore`)。
- 空の`dialog/`はgitに残らない(gitは空のディレクトリを管理しない)。
- `prompt.txt`(台詞の生成プロンプトの出力例)も、ゴールデンの重要なファイルとして含む。

## 6. 生成AIに識別子を決めさせない・出力例に具体的な値を書かない(2026-09-29ユーザー決定)

- `scene_id`等の識別子はシステムが決める。生成AIの出力に含まれていても使わず、システムが付け直す
  (`scene_generator`)。出力例に`scene_id: "scene_000"`と書いたところ、生成AIが`scene_001`に変え、
  ファイル名と原稿の中身が食い違った。
- プロンプトの出力例(`OutputFormat`のテンプレート)は、記入欄(`<…>`)で書く。具体的な値を書くと、
  生成AIがそのまま写す(`title`、16件すべての`context`が出力例と同じになった)。

## 7. SQLite

- SQLiteを使う。ただし、QIDMのdomain.dbとは構造も目的も異なる。QIDM由来の記述(Domain・Run・domain.db等)を
  流用しないこと。
