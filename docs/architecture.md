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
| `gis/` | (独立) | 地理情報(GIS)の汎用ライブラリ(2.2節) |
| `infra/io/`・`infra/store/` | B | 外部とやり取りする形式との変換(モデル定義YAML)・内部状態の永続化(`*_store`) |
| `service/process/` | B | 内部の処理。`production/`=制作の流れの各工程(`dialogue_generator`・`scene_generator`・`sound_generator`)、`edit/`=プロジェクト・設定・Datasetの手順、`genai/`=生成AIを使う処理 |
| `service/api/` | C | 公開API(`project`・`preference`・`dataset`・`drama_model`・`drama_draft`) |
| `schema/` | C | 契約(pydantic)。`api/`=公開APIのDTO、`formats/`=ディスクに残るファイル形式 |
| `api/`(core外) | C | インターフェース: HTTP |

### 依存方向(2026-09-29ユーザー決定、QIDMに合わせる)

- インターフェース(`api`等)→`service/api`→`service/process`→`infra`→A(`model`・`project`)の一方向。
  `schema`は契約・ファイル形式の型として各層から参照される。
- A(`model`・`project`)は`infra`・`service`・`schema`・`genai`をimportしない。`infra`は`service`を、
  `service/process`は`service/api`をimportしない。
- `prompt`は`genai.prompt`(プロンプトの部品)と`model`だけを使う。
- `genai`はパッケージの外を一切importしない。生成AIを呼ぶのは`service/process`。
- `gis`もパッケージの外を一切importしない。使うのは`infra`・`service`(`model`は使わない。形はWKTの文字列で持つ)。

### ファイルの命名規則(2026-09-29ユーザー決定、QIDMに合わせる)

- **A. 静的な状態の定義**(`model`・`project`・`prompt`): 定義する概念の単数形の名詞。役割の接尾辞は付けない。1ファイルに1系統の定義。
- **B. 動的な処理**(`infra/io`・`infra/store`・`service/process`): 「対象_役割」(例: `dialogue_generator`)。
  フォルダ名は役割ではなく処理の分野。
- **C. 外部との境界**(`schema`・`service/api`・`api`): `schema/api`・`service/api`・`api/routers`は同じリソース単位の
  単数形の名詞で1対1に対応させる。
- **共通**: 英小文字のsnake_case。内部専用のモジュールは先頭に`_`。
- **型注釈**(2026-09-30ユーザー決定): `Optional[X]`・`Union[A, B]`(`typing`)で書く。`X | None`・`A | B`(`|`で並べる書き方)は使わない
  (読み込むツールが対応していないことがあるため)。ruffのpyupgradeの`UP007`・`UP045`は無効にしている(`pyproject.toml`)。パッケージは現在の規模ではなく、長期的な責務の境界で切る
  (1ファイルだけのパッケージでもよい)。

## 2. 生成AIライブラリ(`core/genai/`)は独立させる

- 他のプロジェクトでも使う独立したライブラリの候補なので、パッケージの外(`core.*`等)をimportしない。
  どの設定・APIキーを使うかは使う側が決め、値として`factory`に渡す。
- 抽象の契約は`generator.py`(`TextGenerator`・`SpeechGenerator`・`EmbeddingGenerator`)。
  具象は`gemini/`・`openai_compatible/`(llama.cpp・Ollama・Open WebUI)。提供元の違いは`factory.py`に集める。
- 提供元の具象は任意の依存(google-genai等)を必要とするため、使うときに初めてimportする。
- 音声合成は現状Geminiのみ(`SPEECH_CLIENTS`)。
- **構造化出力の落とし穴**(2026-10-02、Gemini APIの`gemma-4-31b-it`で確認):
  - Gemmaは、出力の形を`response_schema`で縛ると、文の途中から同じ語を繰り返して出力の上限まで止まらないことがある
    (上限を決めていないと10分以上返らなかった)。Gemini用の生成器は、モデル名が`gemma`で始まるときは`response_schema`を渡さず、
    JSONで返すことだけを指定し、形(JSON Schema)を指示の文に足す(`gemini/generator.py`の`schema_in_prompt`)。この形で約1分で正しく返った。
  - JSONモードでもコードの囲み(```json … ```)を付けて返すモデルがあるので、構造化出力は最初の`{`から最後の`}`までを読み直す
    (`generator.py`の`parse_structured`。Gemini・OpenAI互換の両方)。
  - 生成AIを呼ぶ処理は、応答の長さに上限(`TextConfig.max_output_tokens`)を設け、繰り返しに陥っても上限で止めて
    「途中で切れた」(`OutputTruncatedError`)と知らせる(Build with AIは8192)。

### 2.1 文章生成は作品作り用と作業補助用の2つ(2026-10-02ユーザー決定)

- `project.yaml`の`genai`は、文章生成を`creative_llm`(作品作り。台詞・演出等、品質が要る。課金のある高機能な生成AIを想定)と
  `assistive_llm`(作業補助。骨組みの作成等。課金の無い生成AI(Google AI StudioのGemma・手元のllama.cpp等)を想定)に分けて持つ。
  GUIはProject OverviewのGenerative AIタブで2つの欄に分ける。旧来の`genai.llm`は読まない(互換性は考えない)。
- **タスクごとにどちらを使うかは、処理の側の対応表1か所で決める**(`core/service/process/genai/llm_role.py`の`TASK_LLM_ROLES`。
  タスクは`AgentTask.code`で示し、エージェントに属さない処理も同じ名前空間のcodeを足す)。作業補助に回すタスクは作業の過程で増えるので、
  タスクを足す・役割を移すときは表だけを直す。モデル(`core/model`)には持たせない。生成器は`generator_builder.build_task_text_generator`
  (タスクから)か`build_text_generator(project, LlmRole)`で作る。
- **未設定の役割を、もう一方の役割で代わりに動かさない**(作業補助が未設定なら、作品作り(課金あり)で黙って動かさずにエラーにし、
  設定を促す)。表に無いタスクもエラーにする。
- 既存のタスクは、2026-10-02時点ですべて`creative`(それまでの動きのまま)。作業補助に回すタスクは、作るときに決める。

### 2.2 GISの機能は`core/gis/`に集める(2026-10-02ユーザー決定)

- 地理情報の処理(形の検査・変換、ファイル形式の読み書き、空間の関係)は`core/gis/`に置く。`core/genai`と同じく、他のプロジェクトでも
  使える独立したライブラリとし、パッケージの外をimportしない(パッケージの中は相対import。`tests/core/test_gis_independence.py`)。依存はshapelyだけ。
- **分け方は機能の種類**: `geometry.py`(WKTの検査・正規化、GeoJSONとの変換)・`feature.py`(地物の型)・`io/`(`geopackage.py`・`kml.py`)・
  `analysis/`(`containment.py`=点を含む面。後に距離・隣接等)。edit・view・analysisの用途で分ける案は採らなかった(地図の表示はGUIの役目で、
  GeoJSONとの変換は表示と編集の両方が使い、境界がはっきりしないため)。
- **Location・SiteFlow等のAIDCの意味づけは使う側に残す**: 層の名前による振り分け(`infra/io/geodata_reader.py`)、移動の端点の検査
  (`infra/io/model_definition_reader.py`)、下書きへの部分YAML(`service/process/edit/geodata_importer.py`)。

## 3. APIキー

- **リポジトリにキーを置かない。** コードへの直書き・project側の設定ファイルへの保存もしない。
- キーは利用者のホームの`~/.aidc/secrets.env`(`AIDC_SECRETS_PATH`で変更可)に保存し、そこからだけ読む。シェルの
  環境変数(`GEMINI_API_KEY`等)からは読まない。制作の流れ(`main.py`)もこの方式に移した(2026-09-29ユーザー決定)。
  キーの名前は提供元と接続先から決まる(`generator_builder.api_key_name`。例: `AIDC_GEMINI_API_KEY`)。

## 4. 作品とエージェントのモデル(`core/model/`)

- 作られる作品は`core/model/drama/`、作品作りに参加するエージェントは`core/model/agent/`に定義する(2026-09-30ユーザー決定)。
  中のクラスの構成は2026-10-01にユーザーが承認した([model_design.md](model_design.md)。**暫定**と書いた箇所は暫定のまま)。
- **モデルの設計などは素のクラスで書くことを優先する**(2026-09-30ユーザー。QIDMの`core/model`と同じ)。`dataclass`は禁止では
  ないが、ユーザーが基本的に好まないため、必要なときだけ許可を得て使う。モデルに`dataclass`が合わない理由は、`__eq__`が値の比較に
  なって識別子で同一性が決まるエンティティと食い違うことと、属性が外から書き換えられて不変条件をメソッドで守らせにくいこと。pydanticにも
  しない(pydanticは`core/schema/`の契約・ファイル形式の役割)。各エンティティは`__init__`で`self.id = new_id()`を振る。
- **`core/model/`には純粋なモデルだけを置く**(2026-09-30ユーザー決定)。API・生成AI・ファイル・DBに関わるもの(ファイルのパス・
  Datasetのfile_id・生成AIへの指示・生成器・pydantic・読み書き)を置かない。`core.model`は`core.model`の外をimportしない。
- エージェントのモデルには、エージェントどうしのやり取り(発注・提案・相談)と、動かす手段(生成AIの種類等)を置かない。
- **エージェントは生成AIが担う職能で、抽象クラス`BaseAgent`の下に置く**(2026-10-01ユーザー決定)。プロンプトを組み立てるための情報
  (役割・性格づけ・厳守事項・禁止事項・タスク`AgentTask`)を属性として持ち、プロンプトの文は持たない(組み立ては`core/prompt`)。
  作品ごとに書き換える(`Dramaturgy.agents`。作品の下書き・版・DBに入る)。Producerは利用者本人なのでモデルに置かない。
- **エージェントの既定は、システム既定(`core/default/agents/`のYAML。正本)とプロジェクトのユーザー既定(`<プロジェクト>/user_default/agents/`)
  の2段**(2026-10-02ユーザー決定)。プロジェクトの作成時にシステム既定を複製する。既定のYAMLは`core`の側に置く(プロジェクトの作成は
  `core`の処理で、インターフェース(`apps`)に依存しないため。当初`apps/AIDC-Console/default/`に置いたものを移した)。
  詳細は[model_design.md](model_design.md)「`core/model/agent/`」。

## 5. 実験用のプロジェクトと、旧来の形(2026-10-01ユーザー決定)

- 実験用のプロジェクトは`Project/TEST_PROJECT_##`(リポジトリ直下、`##`は01からの連番)に、`apps/sample_data/`を複製して作る
  (作品のディレクトリ(例: `令和但馬道中膝栗毛/`)の`drama/`・`agent/`を`model/`に、`apps/sample_data/project.yaml`を直下に)。`apps/sample_data/`を直接`root_dir`にしない。`Project/`はgitの管理外。
- 旧来の形(`apps/sample_project`のテキストのファイル、`<root_dir>/project/`の下の構成)は使わない。互換性は考えず、移行が済んだものは
  設計も含めて残さない。`apps/sample_project`と旧来の`Project`(`_legacy_project.py`)は削除した。

## 6. 生成AIに識別子を決めさせない・出力例に具体的な値を書かない(2026-09-29ユーザー決定)

- `scene_id`等の識別子はシステムが決める。生成AIの出力に含まれていても使わず、システムが付け直す
  (`scene_generator`)。出力例に`scene_id: "scene_000"`と書いたところ、生成AIが`scene_001`に変え、
  ファイル名と原稿の中身が食い違った。
- プロンプトの出力例(`OutputFormat`のテンプレート)は、記入欄(`<…>`)で書く。具体的な値を書くと、
  生成AIがそのまま写す(`title`、16件すべての`context`が出力例と同じになった)。

## 7. SQLite

- SQLiteを使う。ただし、QIDMのdomain.dbとは構造も目的も異なる。QIDM由来の記述(Domain・Run・domain.db等)を
  流用しないこと。

### 作品モデル(`core/model/drama`)のDB(2026-10-01ユーザー決定)

テーブルの定義と実装の場所は [database_design.md](database_design.md)(2026-10-01承認・実装)。

- **DBが正本**。モデル定義YAMLは、取り込み・書き出しと、生成AIとの受け渡しに使う。
- 対象は`core/model/drama`と、作品が所有するエージェント(`core/model/agent`。2026-10-01から)。Datasetの台帳は後で。
- **版と下書きの単位は、プロジェクトの作品モデル全体**(Dramaturgyごとにしない)。人物・人物関係はProjectが持ち、
  複数の作品から参照されるため。
- 3つの層: ①今の状態(正本。作品のテーブル)・②下書きの履歴・③版。
- **提案はApplyしても下書きにだけ入る**(QIDMのdraftsと同じ)。下書きはDBに置き、Apply・直接編集・Undoのたびに
  作品モデル全体の写しを1版ずつ積む(Undoは1つ前と同じ内容を新しい版として積み、履歴は消さない)。
- **正本を変える経路は、下書きの確定だけ**。YAMLの取り込みも、下書きを作って確定する。
- **確定=版の作成**。確定すると①を書き換え、③に版を1つ足す(明示的な保存は確定が兼ねる)。
- 下書きの元にした版(`base_version`)が今の版と違えば、確定を拒否する(作り直してもらう。差分の統合は後で考える)。
- ②・③の写しはモデル定義YAMLの文字列。プロジェクト全体を写すため、モデル定義YAMLの最上位に`dramaturgies:`の一覧を足す。
- 置き場所はプロジェクトの`project.db`(Datasetの台帳と同じDB)。
- **project.dbはGeoPackageとしても読める**(2026-10-02ユーザー決定)。場所(`location`)と場所の間の移動(`site_flow`)は形の列を持ち、
  QGIS等でそのまま開ける。GISの道具からの編集は、KML・GeoPackageの取り込み・書き出しで下書きを通す(書き出しは保留)。詳細は
  [database_design.md](database_design.md)「GeoPackage」。

### 場所の地図の取り込み(2026-10-02ユーザー決定・実装)

- 対象はKML(Google マイマップの書き出しの`.xml`も)・KMZ・GeoPackage。**作品ごとに取り込む**(場所・移動の実体はプロジェクトに入り、
  作品はファイルにあるものを参照する。シリーズの別の作品の場所まで並ばないように)。形の決まりは`apps/AIDC-Console/templates/README.md`。
- 層(KMLのフォルダ・GeoPackageの表)の名前が`Location`・`SiteFlow`(大文字・小文字と`_`・空白を無視)のものが場所・移動、それ以外はすべて補助情報。
- **取り込み直しはファイルの内容で置き換え**: 場所は属性`id`が同じものを更新し、作品の参照(`locations`・`site_flows`)はファイルのもので
  置き換える(プロジェクトの実体は消さない)。移動は`id`か、この作品の移動のうちorigin・destinationが同じものを更新する。
- 移動のorigin・destinationは、線の始点・終点を含む場所の面から決める。**どの面にも入らない・2つ以上の面に入る端点があれば、取り込み全体を断る**
  (問題のある線をすべて示す。下書きは変わらない)。
- **補助情報は、作品に割り当てたDataset**(`<取り込んだファイル名>_補助情報.gpkg`。`dataset_registry.drama_id`に作品のid)として保存する。
  Datasetは下書きを通らず、すぐに保存される(取り込み直すと同じファイルを上書きする)。
- KMLはGDAL(LIBKML)ではなく標準のXMLで読む(LIBKMLはExtendedDataの`id`・`description`とKML自体の要素を同じ列にまとめ、
  Google マイマップの書き出しで値が混ざるため)。GeoPackageもsqlite3で読む(形式の読み書きは`core/gis/io/`の`kml.py`・`geopackage.py`、層の振り分けは`core/infra/io/geodata_reader.py`)。
  依存はshapelyだけで、GDALは要らない(GDALで変換したGeoPackageも読める。属性の名前は大文字・小文字を区別しない)。
- 実装: `core/service/process/edit/geodata_importer.py`(下書きへの部分YAML)、公開APIは`drama_draft.import_geodata`
  (`POST /projects/{id}/drama-drafts/{draft_id}/import-geodata`。ファイルはbase64)、GUIはLocationsタブのImport KML / GeoPackage...。

### Projectの役割(2026-10-01ユーザー決定)

- `Project`(`core/project/project.py`、project.yaml)は、プロジェクトのメタ情報(id・名前・日時)と設定(生成AIの接続先等)だけを持つ。
  作品モデル(作品・人物・人物関係・時点・場所)はProjectのクラスに持たせず、DBの正本として扱う(組み立てた結果は`ModelDefinition`)。
- `ModelDefinition`の置き場所は`core/infra/io`(モデル定義YAMLの読み込み結果)のままでよい。

### 作品モデルの公開API(2026-10-01ユーザー決定)

- 既存の`project`・`dataset`と同じ作り方: HTTPはYAMLでやり取りし(`api/yaml_io.py`)、`/projects/{project_id}/...`の下に置く。
- リソースは`drama_model`(正本と版。読むだけ)と`drama_draft`(下書きの作成・一覧・中身・履歴・取り込み・Apply・直接編集・
  Undo・確定・破棄)の2つ。`service/api`・`schema/api`・`api/routers`に同名のファイルを置く。
- 作品の中身のDTOは、モデル定義YAMLの形(`DramaturgyDefinition`)で兼ねる(取り込み・生成AIとの受け渡し・GUIが同じ形)。要素は`id`で特定する。
- 部分的な反映は**idで重ねる部分YAML**: 変えたい部分だけをモデル定義YAMLの形で渡し、下書きの中身に重ねる
  (同じidの要素は上書き、idの無い要素は追加、削除は明示的に書く)。細かい規則は [database_design.md](database_design.md)。

## 8. Web GUI(AIDC Console)(2026-10-01ユーザー決定)

- GUIは`apps/AIDC-Console/`に、QIDM Console(QIDMの`apps/QIDM`)にならって作る。ビルド不要の素のHTML/CSS/JSで、
  `static/vendor/js-yaml.min.js`をベンダリングする。APIサーバー(`api/main.py`)が`/app`に静的ファイルとしてmountする。
- 画面の構成: 上部にメニューバー、左にTree、右にパネルの入れ物(main-area。一度に1つのパネル)。**Propertiesの区画は置かない**。
- **メニューの表記は英語**(Project・Connection…)。
- QIDMのGUIのファイルは、実行時に参照せず**複製して直す**(別リポジトリに依存しないため)。
- **APIサーバーの既定のポートは8100**(QIDMの8000と競合するため。`scripts/server/start.sh`の`AIDC_SERVER_PORT`・
  `core/project/project.py`の`DEFAULT_SERVER_BASE_URL`・`app.js`の`DEFAULT_SERVER_BASE_URL`・`apps/sample_data/project.yaml`を揃える)。
- パネルはShadow DOMを使わない(light DOM)Custom Elementとし、`app.css`の共通クラス(`.field`・`.btn`・`.panel-*`等)を使う。
- メニュー: Project・**Edit**・Connection。Editに`New Dramaturgy...`(題・幕数・言語。空の幕を持つ作品を作り、すぐに確定する)と
  `Dramaturgy Editor`(Treeで選んだ作品。QIDMのDomain Editorにあたる)、`Edit Location on Map`(下の「地図の上での場所の編集」)。
- **Dramaturgy Editorは編集用の下書きを通す**(正本を変えるのは下書きの確定だけ、7節): 題が`Dramaturgy Editor`のopenな下書きを
  プロジェクトに1つ持ち、各タブのSaveは部分YAMLの直接編集(`edit`)、ヘッダーの`Save Version`が確定(版を1つ作る。QIDMのSave Schemaに
  あたる。未確定の変更があれば緑)。確定したら新しい版から下書きを作り直す。下書きの元の版が古ければ、変更が無ければ黙って、
  あれば利用者に確かめてから破棄して作り直す。Saveのたびに確定する案(Saveごとに版が増える)は採らなかった。
- 幕数は、Actsタブでの幕の追加・削除で決める(Propertiesに数の欄は置かない)。
- タブ: Properties・Proposal(企画書)・Agents(エージェント)・Locations・Acts・Scenes・Recording。Agentsタブは作品のエージェントの文面を書き換える。
  - **言語はプルダウンで選ぶ**(2026-10-06ユーザー決定・実装): Input Language・Output Language(とNew Dramaturgyの同じ欄)は、システム既定の
    言語の一覧(`core/default/languages.yaml`。BCP 47のコード・その言語での名前・日本語の名前。日本語・英語・中国語(簡体字・繁体字)・韓国語・
    フランス語・スペイン語等18)から選ぶ。API: `GET /languages`。一覧に無い今の値も選択肢に残す。
  - **訳文は言語ごとにいくつでも持つ**(2026-10-06ユーザー決定): 観光地向けに少なくとも日本語・英語・中国語・韓国語、多くはフランス語・
    スペイン語も要る。Output Languageは**既定の音声の言語**(Auditionで声を選ぶ言語、ScenesタブのTranslationの最初の言語)で、作品の
    モデルは変えない(1つのまま)。原稿の台詞は`Dialogue.translations`(言語と訳文の組の一覧。同じ言語は1つ)を持つ(旧`translated_text`は廃止)。
  - Casts: 配役ごとの既定の声(Actor)に加え、**Voices by Language(言語ごとの声)**(2026-10-06ユーザー決定・実装): 既定の声の言語以外の作品の
    言語(制作の言語・既定の音声の言語・訳文のある言語と、設定済み・利用者が足した言語)ごとに、その言語の声の一覧から選ぶ(「既定の声を
    使う」も選べる)。一覧は丸ごと置き換えて保存する。配役のLanguageも言語のプルダウン。
  - Recording(2026-10-05ユーザー決定・実装): 言語を選び、演出付きの原稿(`Scene.elements`の`Dialogue`)から**シーンごとに1つの音声(mp3)**を作る。
    シーンごとのRecordと、作れるシーンを順に作る**Record All**(1シーンずつ要求する。Stopで今のシーンの後に止まる)。生成した音声はタブで再生・ダウンロードできる。
    - 足りないものには、原稿が今の台詞と食い違う行(ScenesタブのScriptで原稿の後に台詞を直した)も入る。
    - 言語は、制作の言語(Input Language。原稿の音声にする文を読む)・既定の音声の言語(Output Language)・作品のどこかの台詞に訳文のある
      言語(どれもその言語の訳文を読む。言語の一覧の順)。
    - **足りないものがあるシーンは断る**(課金の無駄を防ぐ): 台詞が無い・演出付きの原稿の無い台詞・その言語の文(訳文)の無い台詞・声の決まっていない配役。
      一覧でシーンごとに示し、Recordを押せなくする(サーバーも音声合成を呼ばずに400)。
    - 台詞の順に、演者(`Actor`)の声で台詞1行ずつ音声合成し、台詞の後の間(`pause_after`。Short=300ms・Medium=700ms・Long=1500ms、
      無ければShort)を挟んでつなぐ(pydub・ffmpeg)。**声は、演者に読む言語の声(`Actor.voices`)があればそれ、無ければ既定の声**
      (`voice_name`。提供元・モデルが空なら演者の既定、それも空ならproject.yamlの`genai.tts`)。既定の声の言語(配役の言語、無ければ作品の
      Output Language)と違う言語を既定の声で読む演者は、シーンごとに知らせる(作れるが確かめるとよいこと。`notices`)。
    - **音声合成への指示**(`core/prompt/recording.py`。2026-10-06ユーザー決定「自動で直す」・実験で確認): 見出しに番号を付けない素のMarkdownで、
      声の性別・ト書き・Directionの英語の演出(話し方・速さ・強弱・感情)と、「TRANSCRIPTだけを、その言語で読む」を渡す。**利用者が書いた設定
      (人物の名前・演じ方・話す速さ・訛り・場所・状況)は、どの言語でも渡さない**。渡すと、音声合成がそれを読み上げたり、それを元に台本に
      無い台詞を作って話したりした(日本語専用の声に日本語の設定と英語の台本 → 設定を読み、台本を日本語に訳し戻した。日本語の台本でも、
      設定から作った前置きを話した(2回とも)。設定を渡さなければ、日本語・英語とも、日本語専用の声でも台本どおりに読んだ)。
    - **保存先はプロジェクトのフォルダ**: `<プロジェクト>/recordings/<作品のid>/<言語>/<シーンのid>.mp3`(`recording_store`)。生成し直すと上書きし、
      失敗したら前の音声を残す。作品の版(Save Version)とは結び付けない。原稿は編集用の下書き(画面に出ている内容)から読む。
    - API: `GET /projects/{id}/recordings`(言語と、シーンごとの足りないもの・音声の有無)・`POST .../recordings`(1シーンを作る。音声合成の失敗は502)・
      `GET .../recordings/{作品}/{言語}/{シーン}.mp3`(音声)。処理は`core/service/process/production/scene_recorder.py`。
    - `main.py`の音声の生成(旧来の`work/scene/`の原稿と30声の表)とは別の処理(known_issues.md)。
  - Locations(2026-10-02): 作品が参照する場所と、その間の移動(SiteFlow)。地図の取り込み(Import KML / GeoPackage...。7節)、
    場所の名前・案内・事実を書き換え(場所はプロジェクトで共有)、
    移動の向きを決める。形は表示だけ(編集はEdit Location on Mapか取り込みで)。**Generate Scenes**は、シーンの無い場所から選んだ幕にシーンを機械的に作る
    (題=場所の名前、場所=その場所。生成AIは使わない)。並びは移動を辿った順(入ってくる移動が無い場所から深さ優先。どの移動にも
    つながらない場所は末尾)。
  - Scenes(2026-10-02): すべての幕のシーンの一覧と、題・あらすじ・場所の編集、追加・削除(削除したら同じ幕のorderを詰める)。
    シーンの詳細はPlot・Script・Translationのタブに分ける(2026-10-05ユーザー決定・実装):
    - Script: 台詞の行(話者=配役・台詞)の編集・追加・削除(Build with AIのScriptの工程の右側と同じ部品)。**演出付きの原稿があっても編集できる**。
      台詞を消すと、その行の原稿(演出・訳文)も同じ直接編集で消す。文言を変えた行の原稿は残し、「原稿と食い違う」と示す
      (原稿の音声にする文から感情タグと空白を除いたものが台詞と違う)。Recordingは食い違う行のあるシーンを作らない(Directionで作り直す)。
    - Translation: **言語を選び**(制作の言語以外の一覧。既定はOutput Language。訳文のある行の数も示す)、台詞ごとの原稿のその言語の訳文
      (`Dialogue.translations`。Recordingでその言語の音声を作るときに読む)を編集する。**Translate**で生成AIが
      シーンの全行を選んだ言語へ訳して欄に入れる(下書きは変えない。確かめて直してからSave)。担当はStageManagerのタスク`translate`
      (model_design.md。作品のもの、いなければユーザー既定)。訳すのは原稿の音声にする文(感情タグ入り。同じ所に同じタグを挿ませ、
      一覧に無いタグは外す)で、原稿が無い・今の台詞と食い違うなら台詞。Saveは、原稿のある行は訳文の一覧のその言語だけを書き換え
      (ほかの言語の訳文は残す。空にするとその言語の訳文を消す)、原稿の無い行は訳文を書いたときだけ台詞のままの原稿を作る。Input Languageが要る。
      API: `POST /projects/{id}/drama-drafts/{draft_id}/scene-translation`(訳文を返すだけ)。処理は`core/service/process/genai/scene_translator.py`、
      プロンプトは`core/prompt/scene_translation.py`。
  - エージェントは利用者が足さない(既定から読み込む。2026-10-02ユーザー決定)。New Dramaturgyはユーザー既定の6職能を必ず入れ、
    Agentsタブを開いたとき足りない職能はユーザー既定から自動で下書きに読み込む(未確定の変更になる)。追加・削除の操作は置かない。
  - Reset to Default=作品のエージェントをユーザー既定で置き換える。Save as User Default=今の入力をユーザー既定にする。
    Restore System Default=ユーザー既定をシステム既定に戻す(作品は変えない)。空にした項目はシステム既定になる(部分YAMLの`null`)。
  - Actor(演者)は出さない(置き場所は保留)。幕の`order`は0から連番で、削除したら詰める。
- New Dramaturgyは別の下書きで作品を足して確定するため、Dramaturgy Editorの下書きに未確定の変更があれば断る(先にSave Versionを求める)。

### 地図の上での場所の編集(Edit > Edit Location on Map。2026-10-02ユーザー決定・実装)

- **Leaflet + Leaflet-Geoman(無料版)**を`static/vendor/`にベンダリングする(どちらもMIT。ビルド不要の1ファイル)。頂点をクリックして描く形で十分なため
  (ペンで描く手書きは要らない。頂点の間引きもしない)。背景は地理院タイル(既定は標準)とOpenStreetMap。タイルの取得にはインターネットが要る。
- Treeで選んだ作品が対象。**面を描くとLocation、線を描くとSiteFlow**。選んだ地物の属性(Locationは名前・住所・案内・事実、SiteFlowは名前・向き)を右の欄で書く。
- 保存の経路はDramaturgy Editorと同じ: **Saveで編集用の下書きへ(直接編集)、Save Versionで確定**。地図の変更はSaveまで画面の中だけにあり、
  Save Versionは先にSaveする。画面とサーバーは形をGeoJSONでやり取りし、WKTへの変換はサーバー(`core/gis/geometry.py`)で行う
  (緯度・経度の順の取り違えを画面に持ち込まない)。
- **保存は「画面の地図の状態を取り込む」のと同じ規則**(`geodata_importer.build_patch`を共通に使う。`core/service/process/edit/location_map_editor.py`):
  移動のorigin・destinationは線の始点・終点を含む面から決め、**どの面にも入らない・2つ以上の面に入る端点があれば保存全体を断る**(面を動かして
  端点が外れた場合も同じ。移動を未接続のまま残すことはしない)。地図から消した場所・移動は作品の参照から外す(プロジェクトの実体は消さない)。
  形の無い場所・移動は地図に出ないので参照をそのまま残す(一覧のDraw Shapeで面を描ける)。
- **補助情報(作品のDatasetのGeoPackage)は表示だけ**。Datasetは下書きを通らずにすぐ保存されるため、同じ地図で保存の時機が異なると紛らわしい。
  編集は、困ったときに改めて考える。

### GUI実装上の落とし穴(QIDMから引き継いだもの)

- **`[hidden]`属性のCSS競合**: `app.css`冒頭の`[hidden] { display: none !important; }`を削除しない
  (`display`を明示するクラスを持つ要素(`#modal-backdrop`等)が隠れなくなり、画面全体がクリック不能になる)。
- **`.toast`はクリックを透過させる**(`pointer-events: none`)。重なる位置のボタンのクリックを奪う不具合があった。
  この種の不具合はDOMの`.click()`では再現しないので、座標ベースのクリックで確かめる。トーストの種類は`error`・`warn`・`info`・`ok`の4つ
  (`showToast(message, kind)`)。完了したが確かめることがあるものは`warn`にし、赤(`error`)にしない。
- **main-areaのパネルの`display`**: Custom Elementは既定で`display: inline`のため、`#main-area > *`を一律に
  flex columnにしている(QIDMはタグ名の列挙で、追加漏れでスクロールが効かなくなった)。main-areaの直下にはパネルだけを置く。
- **`.field`と`.panel-form-row`を同じ要素に付けない**(`flex-direction`が中途半端に残る)。横並びは`.panel-form-row`の下に`.field`を並べる。
- **表**: `.data-table-wrap`(`.data-table`と組)を使い、表がその区画の主な内容なら`.data-table-wrap--fill`で残りの領域を埋める
  (直後に常に見せたいボタンがある場合は付けない)。`.panel-body`直下の他の要素は`flex-shrink: 0`で潰れない。
- **複数ファイルの保存にフォルダ選択(`showDirectoryPicker`)を使わない**(Chromeがホーム等のフォルダを拒否する)。
  サーバー側でZIPにまとめ、`saveBlobToFile`(`showSaveFilePicker`)で1回で保存する。


## 9. 人物パネルとCasting(2026-10-02ユーザー決定。人物パネル・企画書の取り込み・Castsタブ・Build with AIのCasting/Auditionは実装済み)

前提は「世界観が先、作品は後」([overview.md](overview.md))。人物はプロジェクトに登録し、作品はそこから使う。

- **人物パネル**(プロジェクト全体。Treeで作品を選んでいなくても開ける): Characters・Groups・Relationshipsのタブ。
  どの作品からも使われない人物・設定の少ない人物(通行人A等)を、不備として扱わない(警告・必須にしない)。
- **Castsタブ**(当初の呼び名はCastingタブ)は Dramaturgy Editor(作品)に置く。流れは、①人物の設定(人物パネル)→②誰を主役・脇役にするか→③役に合う
  配役の条件→④Audition(条件に最適な、音声合成のモデルと話者を生成AIに選ばせる)→演者(`Actor`)の決定。Actorの設定もここで行う。
  - 主役・脇役・端役は`Cast.billing`(lead・supporting・minor。2026-10-02)。台詞の無い人物には配役が無い。`Cast`の演じ方・声の性別・言語・訛りがAuditionの条件になる。
  - Castsタブ(2026-10-02実装): 配役の一覧(作品の登場人物から足す)・役の重さ・演じ方・声の条件の編集・削除(演者も消す。台詞が使う配役は参照切れで断られる)、
    演者の声の選択(声の一覧は配役の言語、無ければ作品の言語で絞る。保存すると演者が無ければ作り、提供元・モデルは一覧を取った音声合成の設定)。
  - Auditionの対象は人物ではなく、音声合成の話者(演者)。担うのはCastingDirectorの`assign_voice`。
  - **`Actor`は音声合成の提供元・モデル・話者を持つ**(文章生成と音声合成は仕事が違うため、「どの生成AIで動かすかはモデルに持たない」
    の例外。4節)。音声合成の設定は、Auditionの候補として複数持てる形にする(当面は1つでよい)。
  - 話者とその特徴の一覧は`core/genai`で提供元から取得する(`SpeechGenerator.list_voices`。Geminiは`GET /v1beta/voices`。性別・声の高さ・訛り・言語・persona・
    説明)。取得の手段が無い提供元では、利用者が自分で調べて入れる(当面は許容)。2026-10-02に確かめた: Geminiは約2,100声(日本語は115声。
    年齢・職業・訛り(大阪弁等)の説明付き)をページに分けて返す。提供元・モデルごとに1時間覚えておき、言語は手元で絞る
    (`core/service/process/genai/voice_catalog.py`。公開APIは`GET /projects/{id}/voices?language=ja`)。
- **企画書との連携**: 企画書の登場人物とプロジェクトの人物を照らし合わせる。
  - 企画書の登場人物がまだ登録されていなければ、新しい人物として登録する(骨組みは作業補助の生成AIで作る。`assistive`)。
  - 登録済みの人物が新しい作品の企画書で抜擢された場合、矛盾があればその理由を示して警告し、キャンセル・統合・置き換えを選ばせる。
    キャンセルしたら、利用者が別の名前にするか矛盾を解消する。矛盾の理由は提示・保存・再確認できる必要がある(仕組みは保留)。
  - 企画書の段階で登場人物が未定(0人)でもよい。
  - 取り込みの細部(2026-10-02ユーザー承認): 同じ人物の判断は名前の完全一致(前後の空白は無視)。取り込んだ人物は作品の登場人物の参照にも加える。
    結果は確認の画面を挟まずに下書きへ入れる(Undo・編集で直す)。生成AIはScriptwriterのタスク`import_proposal_character`(骨組み・統合)と
    `check_character_conflict`(矛盾の確認)で、どちらも作業補助。置き換えは識別子を保ち、経歴・人物関係は残す。

## 10. Build with AI(生成AIと相談しながら作る。2026-10-02ユーザー決定)

- **パネル**: Edit > Build with AI...(Treeで選んだ作品が対象)。QIDMのBuild Domain from Referencesと同じく、1つのパネルで
  右側のタブ(工程)を切り替えながら進める(工程ごとに別のボタンやパネルを作らない)。左側に参照する資料とチャット、右側に工程のタブと
  その内容のフォーム(直接直してSaveできる)。最初の工程はProposal(企画書)。
- **今開いているタブ(工程)に、相談相手のエージェントとタスクが結び付く**。対応表はサーバーの1か所(`core/prompt/ai_build/step.py`の
  `BUILD_STEPS`。QIDMの`STEP_PROMPTS`にあたる)。Proposal=Scriptwriterの`draft_proposal`。プロンプトの無い工程(Characters・Casting)は
  タブを並べるが選べない。エージェントは作品のもの(Agentsタブの文面)を使い、いなければプロジェクトのユーザー既定から作る。
  Systemはエージェントの節(`core/prompt/agent_instruction.py`)+工程の指示。生成AIはタスクの役割(`llm_role`)で選ぶ。
- **2つのモード**: 対話(相談しながら、必要なときだけ変える項目を提案。生成AIが空で返した項目は変えない)と、
  ワンショット下書き(要望・資料・今の内容から工程の内容を丸ごと提案。Applyすると丸ごと置き換わり、空の項目は消える)。
- **応答の形**(QIDMと同じ): 返事・提案(工程の内容の全体を返させ、変わる部分をプログラムが部分YAMLにする)・根拠・質問・注意。
  提案は必ず提案の欄に入れさせる(返事の文に書くだけにさせない)。構造化出力の項目はすべて必須にし、無い値は空文字で返させる。
- **提案はApplyするまで作品に入らない**。Applyは編集用の下書き(Dramaturgy Editor・人物パネルと共通)に重ね、Undoは下書きの最後の変更が
  その提案の反映であるときだけ戻す。確定はSave Version。
- **会話は作品ごとに1本**で、各発言はどの工程での発言かを持つ。画面に出す会話と生成AIに渡す履歴は、今の工程の発言だけ。Clearは今の工程の
  会話だけを消す。会話は`project.db`の`ai_build_message`(作品の正本は確定のたびに書き直すので、外部キーで結び付けない)。
  シーンごとの工程(`BuildStep.per_scene`。Script)は、各発言がどのシーンでの発言か(`scene_id`)も持ち、会話・履歴・Clearはそのシーンの発言だけ
  (2026-10-05)。
  生成AIの呼び出しに失敗したら何も記録しない(送り直せる)。読めない資料は400で、生成AIの失敗(502)と区別する。
- **資料**: 生成AIがその種類をそのまま読めれば添付し、読めなければテキストにして本文に入れる(QIDMと同じ)。
- 右側のフォームは、チャットの更新では描き直さない(Saveしていない入力を消さない)。Apply・Undo・Save・工程の切り替えで描き直す。
- 企画書のフォームは、Dramaturgy EditorのProposalタブと共通の部品(`proposal_form.js`の`ProposalForm`)。
- **人物の工程は3つのタブに分ける**(2026-10-02ユーザー決定): Characters(Scriptwriterの`create_character`。人物の一覧を作り、
  まとまりと人物関係も大まかに作る)・Groups(`create_character_group`。まとまりの詳細を固める)・Relationships(`create_relationship`。
  人物関係の詳細を固める)。詳細はタブを切り替えて固める。
  - 人物・まとまり・関係はプロジェクト(世界観)のもの。生成AIには登録済みの人物・まとまり・関係と、作品の企画書・登場人物を渡す。
  - 生成AIは識別子を決めず、要素を名前で指す(人物=名前、まとまり=名前、関係=起点・相手の人物と関係の名前)。同じ名前なら更新、無ければ追加。
  - **生成AIには削除させない**(追加と更新だけ。ワンショットでも既存の要素は残す。削除は人物パネルで行う)。空の値では既存の値を消さない。
  - Charactersの工程で出てきた人物は作品の登場人物に加え、新しい人物関係は作品の参照に加える。Charactersの工程のまとまりは
    既存のメンバーを残して足し、Groupsの工程は返したメンバーで置き換える。いない人物を指すメンバー・関係は外して注意を返す。
  - 経歴と人物関係の時期は扱わない(時期の設定が要る。企画書の取り込みと同じ)。
  - 右側は人物パネル(Character Editor)の該当タブを埋め込む(`loadEmbedded`。ヘッダー・タブを隠し、編集用の下書きを共有する)。
  - 提案の部分YAMLは`core/service/process/genai/ai_build_patch.py`、プロンプトは`core/prompt/ai_build/characters.py`。
- **配役の工程は2つのタブ**(2026-10-02ユーザー決定・実装): Casting(CastingDirectorの`cast_character`。配役・役の重さ・演じ方・声の条件)と
  Audition(`assign_voice`。配役ごとに、条件に合う声を声の一覧から選ぶ)。右側はDramaturgy EditorのCastsタブを埋め込む(`loadEmbedded`)。
  - 生成AIは配役を人物の名前で指す(同じ人物の配役があれば更新、無ければ追加)。削除させない。空の値では既存の値を消さない。
    いない人物の配役・決まりに無い値(役の重さ・声の性別)・一覧に無い声は外して注意を返す。配役した人物は作品の登場人物に加える。
  - Auditionに渡す声は、作品の言語(Output Language、無ければInput Language)の声。作品の言語が無ければ断る。選んだ声は演者(`Actor`)の
    話者・提供元・モデルにする(演者がいなければ「<人物>役の演者」を作る)。プロンプトは`core/prompt/ai_build/casting.py`。
- **あらすじの工程はSynopsisのタブ**(2026-10-05ユーザー決定・実装。Relationshipsの後、Castingの前): Scriptwriterの`write_synopsis`で、
  作品全体のあらすじ(メタメタストーリー)と、幕ごとの題・あらすじ(メタストーリー)を書く。シーンのあらすじ(プロット)は次のScenesの工程。
  - **更新だけ**: 生成AIは今ある幕を番号(1から。`order`の順)で指し、幕を増やしも減らしもさせない(幕数は利用者がActsタブで決める)。
    無い番号の幕は外して注意を返す。空の値では既存の値を消さない(対話でもワンショットでも)。
  - 生成AIには、企画書・この作品の登場人物(人物設定)・作品で使う場所・今の作品と幕のあらすじ・幕のシーン(題・場所・あらすじ。食い違わないように)を渡す。
  - 右側はDramaturgy Editorの埋め込み専用のSynopsis(作品のあらすじと全部の幕の題・あらすじを1つのSaveで直す。`loadEmbedded`)。
  - 提案の部分YAMLは`ai_build_patch.synopsis_patch`、プロンプトは`core/prompt/ai_build/synopsis.py`。
- **シーンのあらすじの工程はScenesのタブ**(2026-10-05ユーザー決定・実装。Synopsisの後): Scriptwriterの`write_synopsis`で、シーンごとの題・あらすじを書く。
  - **更新だけ**: 生成AIは今あるシーンを「第N幕のシーンM」(どちらも1から。`order`の順)で指し、シーンを増やしも減らしもさせない
    (シーンは利用者がScenesタブ・Generate Scenesで作る)。無い番号の幕・シーンは外して注意を返す。空の値では既存の値を消さない。
  - 場所・描く時期・状況は変えさせない(生成AIには参考として渡す)。ほかに企画書・登場人物・作品で使う場所・作品と幕のあらすじを渡す。
  - 場所は住所・案内すること(`instruction`)・事実(`description`)を渡す(Synopsisの工程も同じ。`synopsis.location_lines`)。
    シーンの場所の「案内すること」は、そのシーンで人物が聞き手に案内する内容としてあらすじに入れさせ、「事実」と食い違う内容を書かせない。
  - 右側はDramaturgy Editorの埋め込み専用の`scene_synopsis`(すべてのシーンの題・あらすじを1つのSaveで直す)。
  - 提案の部分YAMLは`ai_build_patch.scene_synopsis_patch`、プロンプトは`core/prompt/ai_build/scene_synopsis.py`。
- **読み上げ台本の工程はScriptのタブ**(2026-10-05ユーザー決定・実装。Auditionの後): Scriptwriterの`write_dialogue`で、**1シーンずつ**台詞
  (`Scene.script`の話者と台詞の並び)を書く。演出付きの原稿(`Scene.elements`。Director)は扱わない(後で別の工程にする)。
  - 右側の上でシーンを選ぶ(既定は最初のシーン)。会話もシーンごとに分ける(上の「会話は作品ごとに1本」)。
  - **話者は配役済みの人物だけ**: 生成AIは人物の名前で指し、配役にいない人物の行・空の行は外して注意を返す(画面に出す提案も、反映する行だけ)。
    作品に配役が無ければ断る(Castingの工程を先に)。
  - 提案は、そのシーンの**台詞の全体**(対話でもワンショットでも)。Applyは今の行を順に書き換え(識別子を保つ)、余った行は消し、足りない行は足す。
  - **演出付きの原稿があるシーンは断る**(原稿の台詞は`Line`を識別子で参照するので、置き換えると食い違う)。
  - 生成AIには、作品と幕のあらすじ・前のシーン(あらすじと台詞の終わり5行)・次のシーンのあらすじ・対象のシーンの設定(場所の案内すること・事実、
    時期・状況・あらすじ)・話せる人物(配役の演じ方と人物設定)・今の台詞を渡す。長さは利用者の指定に従い、無ければ台詞全体で350字程度
    (`main.py`の台詞の生成の既定と同じ)。台詞にト書き・話者の名前・括弧書きの動作を書かせない。
  - 右側はDramaturgy Editorの埋め込み専用の`script`(選んだシーンの行を、話者(配役)・台詞・削除で並べ、行を足してSave)。
  - 提案の部分YAMLは`ai_build_patch.script_patch`、プロンプトは`core/prompt/ai_build/script.py`。
- **演出付きの原稿の工程はDirectionのタブ**(2026-10-05ユーザー決定・実装。Scriptの後。音声合成の直前の最後の工程): Directorの`direct_scene`で、
  **1シーンずつ**、台詞の1行ごとに演出付きの台詞(`Scene.elements`の`Dialogue`。台詞・配役と対応付ける)を作る。音声はこの原稿から作る。
  - 項目: 音声にする文(`text`)・ト書き(`action`)・演出(`direction`の話し方・速さ・強弱・感情・後の間)。
  - **音声にする文には、音声合成の感情タグ(旧来の原稿の生成と同じ18種。`direction.AUDIO_TAGS`)だけを挿ませ、台詞の文言は変えさせない**。
    感情タグを除いた文が台詞と違えば台詞のまま使い、一覧に無いタグは外して、どちらも注意を返す。
  - **訳文は作らない**(2026-10-06ユーザー決定。翻訳はStageManagerの担当で、ScenesタブのTranslationで言語ごとに作る)。今の訳文は残す。
  - ト書き・演出は音声合成への指示なので英語(旧来の原稿の生成・音声のプロンプトと同じ)。速さはSlow・Moderate・Fast、後の間はShort・Medium・Long。
  - 提案はシーンのすべての台詞の演出。演出を返さなかった台詞は今の原稿を残し、原稿が無ければ台詞のままの原稿を作る(音声に全行が要るため)。
    原稿のある台詞は識別子を保って丸ごと書き換える(空の値は消す)。無い番号は外して注意。台詞の無いシーンは断る。
  - 効果音・環境音・BGMは扱わない(モデルに中身の属性がまだ無い)。
  - 原稿ができたシーンの台詞はScriptの工程で書き換えられない(上)。右側の**Clear Direction**で原稿(演出付きの台詞)を消すと書き直せる。
  - 右側はDramaturgy Editorの埋め込み専用の`direction`(台詞ごとの欄。原稿の無い台詞は「未演出」)。
  - 提案の部分YAMLは`ai_build_patch.direction_patch`、プロンプトは`core/prompt/ai_build/direction.py`。
  - 音声はこの原稿から、Dramaturgy EditorのRecordingタブで作る(8節)。

