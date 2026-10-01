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
  `Dramaturgy Editor`(Treeで選んだ作品。QIDMのDomain Editorにあたる)。
- **Dramaturgy Editorは編集用の下書きを通す**(正本を変えるのは下書きの確定だけ、7節): 題が`Dramaturgy Editor`のopenな下書きを
  プロジェクトに1つ持ち、各タブのSaveは部分YAMLの直接編集(`edit`)、ヘッダーの`Save Version`が確定(版を1つ作る。QIDMのSave Schemaに
  あたる。未確定の変更があれば緑)。確定したら新しい版から下書きを作り直す。下書きの元の版が古ければ、変更が無ければ黙って、
  あれば利用者に確かめてから破棄して作り直す。Saveのたびに確定する案(Saveごとに版が増える)は採らなかった。
- 幕数は、Actsタブでの幕の追加・削除で決める(Propertiesに数の欄は置かない)。
- タブ: Properties・Proposal(企画書)・Agents(エージェント)・Acts。Agentsタブは作品のエージェントの文面を書き換える。
  - エージェントは利用者が足さない(既定から読み込む。2026-10-02ユーザー決定)。New Dramaturgyはユーザー既定の6職能を必ず入れ、
    Agentsタブを開いたとき足りない職能はユーザー既定から自動で下書きに読み込む(未確定の変更になる)。追加・削除の操作は置かない。
  - Reset to Default=作品のエージェントをユーザー既定で置き換える。Save as User Default=今の入力をユーザー既定にする。
    Restore System Default=ユーザー既定をシステム既定に戻す(作品は変えない)。空にした項目はシステム既定になる(部分YAMLの`null`)。
  - Actor(演者)は出さない(置き場所は保留)。幕の`order`は0から連番で、削除したら詰める。
- New Dramaturgyは別の下書きで作品を足して確定するため、Dramaturgy Editorの下書きに未確定の変更があれば断る(先にSave Versionを求める)。

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

