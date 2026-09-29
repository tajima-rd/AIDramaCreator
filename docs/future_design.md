# 設計協議が必要な未決定の構想

実装の前にユーザーに確認すること。決まったら [architecture.md](architecture.md) へ移し、ここから消す。

## インターフェース(保留)

- 公開API(`core/service/api/`)の形: 識別子・DTO(`core/schema/api/`)・リソースの単位。
- HTTP(`api/`、FastAPI)の要否と、リクエスト/レスポンスの形式(QIDMはYAMLでやり取りしていた)。
- Web GUI・CLIの要否。`main.py`の扱い。

## GUIで扱う制作の準備(2026-09-29ユーザー提供。GUIはQIDMの`apps/QIDM`を参考に設計する)

台詞の生成より前に、利用者が行う準備。各項目の入力の方法(ケース)はユーザーの提示のまま。実装は指示があるまで保留。

| # | 項目 | 必須 | 入力の方法 |
| --- | --- | --- | --- |
| 1 | 前提の知識(地域課題・方針・観光戦略等) | 任意 | ①PDF・Word・Excel等の登録→RAG ②テキストボックスで手入力 ③YAMLのモデル定義ファイルから取り込み ④何も与えない |
| 2 | 物語に関わる知識(市町村史・地域の文献等) | 任意 | ①PDF・Word・Excel等の登録→RAG ②テキストボックスで手入力 ③YAMLのモデル定義ファイルから取り込み |
| 3 | キャラクターの作成 | 必須 | ①YAMLのモデル定義ファイルから取り込み ②生成AIとチャットで相談しながら構築 |
| 4 | キャラクターと読み上げ音声の対応付け | 必須 | ①YAMLのモデル定義ファイルから取り込み ②生成AIとチャットで相談しながら設定 ③人が手動でパラメータを設定 |
| 5 | プロットの作成 | 必須 | ①テキストボックスで手入力 ②YAMLのモデル定義ファイルから取り込み ③生成AIとチャットで相談しながら設定 |

未決定(ユーザーに確認すること):

- 「YAMLのモデル定義ファイル」の形式: 全項目を1ファイルにまとめるか、項目ごとか。書き出し(往復)の要否。
- 1と2の使い分け: 生成AIへの渡し方(前提は常に渡す指示・制約、物語の知識は検索して渡す、等)と、Datasetの
  分類(`DatasetCategory`は現状`reference`だけ)。手入力のテキストの保存の形。
- チャットで相談する方式(3〜5)は、QIDMのdrafts(Build Domain from References。[qidm_reuse.md](qidm_reuse.md) C群)を
  下敷きにするか。「対話方式の制作」と同じ枠組みにするか。
- 3と4は、下の「ドラマの構成要素の再定義」の人物(character)と声・演者(actor)の区別に対応する。

## Projectの作り直し

- `core/model/project.py`(現行のドラマ用)と`core/project/project.py`(QIDM由来)を、1つの設計に作り直す。
- ディレクトリ構成(`actor/`・`character/`・`plot/`・`script/`・`scene/`・`sound/`・`dialog/`・`icons/`・`tmp/`)の要否と、
  project.yaml・プロジェクトのレジストリの要否。
- 生成AIの設定(提供元・モデル・system_instruction・TextConfig等)とAPIキーの保存場所。

## Drama(QIDMのDomainに相当する概念、検討中)

- QIDMのDomainは、Drama(ドラマ)に置き換える方向で検討する(2026-09-29ユーザー)。名前ではなく題を持つ(`drama_title`)。
- Datasetのメタデータと台帳は、仮に`drama_id`・`drama_title`を持つ(現状は常に未割当)。Dramaの定義ができたら、QIDMにあった
  次の機能を戻すか決める: Datasetをドラマに割り当てる、ドラマごとのDatasetの一覧と保存(CSV)。
  QIDMの`domain_version`(Domainの版の管理)は持ち込んでいない。
- `DatasetCategory`は`unspecified`・`reference`だけにした(QIDMの`raw_data`・`correlation_comparison`は、Domainと分析の概念のため削除)。

## Dataset・drafts/

- 必要。現状はQIDMの`Dataset`(datasets/配下の本体とサイドカーのデータメタデータYAML、台帳)をそのまま持ち込んでいる。
  何を置くか(参考資料・生成の途中結果等)は未決定。

## 対話方式の制作(保留。パッケージの移行が終わってから)

- 現状は各工程を生成AIへの1回の依頼(ワンショット)で行っている。次の段階で対話方式にする予定。
- QIDMのdrafts(`drafts/<id>/`に作成途中の成果物・会話・版の履歴を置き、ステップごとに提案をApply/Undoする。
  [qidm_reuse.md](qidm_reuse.md) C群)の枠組みを、先に置いておいてもよい。

## SQLite

- 使う。何を保存するか(構造・目的)は未決定。QIDMのdomain.dbとは異なる。
- 暫定で、プロジェクトに`project.db`を置き、Datasetの台帳(`dataset_registry`)だけを持たせている(QIDMではdomain.dbの中)。
  DBの名前・分け方は、SQLiteの設計で決め直す。

## ドラマの構成要素の再定義(`core/model/`)

- 人物(character)と声・演者(actor)の区別、場面(scene)・台詞(transcript)・演出(DirectorNotes)の構造。
- 提供元に依存する声の一覧(`GeminiVoice`)と音声タグ(`AudioTag`)の置き場所。
- 翻訳(サンプルの`scene_000_ch.yaml`は中国語)を工程として扱うか。
