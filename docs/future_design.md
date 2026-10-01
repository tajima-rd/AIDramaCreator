# 設計協議が必要な未決定の構想

実装の前にユーザーに確認すること。決まったら [architecture.md](architecture.md) へ移し、ここから消す。

## インターフェース(保留)

- 作品モデルの公開APIの形は決まった([architecture.md](architecture.md) 7節、2026-10-01)。HTTPはYAML。
- Web GUIは`apps/AIDC-Console`に作ることに決まった([architecture.md](architecture.md) 8節、2026-10-01)。
- CLIの要否。`main.py`の扱い。

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

- 「YAMLのモデル定義ファイル」の形式は、1ファイルでも分割でも読み書きできる形にした(2026-09-30。2026-10-01承認。[model_design.md](model_design.md))。
  既存のDramaturgyへ一部の区画(例: 人物だけ)を追加で取り込む方法は未決定。
- 1と2の使い分け: 生成AIへの渡し方(前提は常に渡す指示・制約、物語の知識は検索して渡す、等)と、Datasetの
  分類(`DatasetCategory`は現状`reference`だけ)。手入力のテキストの保存の形。
- チャットで相談する方式(3〜5)は、QIDMのdrafts(Build Domain from References。[qidm_reuse.md](qidm_reuse.md) C群)を
  下敷きにするか。「対話方式の制作」と同じ枠組みにするか。
- 3と4は、下の「ドラマの構成要素の再定義」の人物(character)と声・演者(actor)の区別に対応する。

## モデルは「作品」と「エージェント」の2本立て(2026-09-30ユーザー)

- `core/model/`には、作られるべき作品のモデルと、作品作りに参加するエージェントのモデルの両方が要る。参考は
  ユーザー提供の資料「音声ドラマにおけるオブジェクト指向モデルの体系化」(物語・構造/音響・記号論/実行・DSPの3層と、
  Producer・Scriptwriter・Director・Stage Manager・Voice Actor・Sound Engineerの職能、音声キューシート)。取捨選択して設計する。
- 置き場所(2026-09-30ユーザー決定): 作品は`core/model/drama`、エージェントは`core/model/agent`(現行の
  `core/model/drama.py`は作品のモデルの再定義で置き換わる)。
- 職能(2026-09-30ユーザー決定): Producer・**Researcher**・**CastingDirector**・Scriptwriter・Director・
  StageManager・**Actor**・SoundEngineer。
  - **Producerは利用者(人)が担当する。** 生成AIのエージェントではない。前提(項目1)を与え、エージェントの提案を
    反映・却下する。2026-10-01、人なのでモデルには置かないことにした(エージェントは生成AIの職能だけ。architecture.md 4節)。
  - 準備の項目3(キャラクターの作成)の相談相手は**Scriptwriter**(2026-09-30ユーザー決定)。項目5(プロット)と同じ相手。
- エージェントの定義(2026-09-30ユーザー決定。2026-10-01に、作品ごとに書き換える形で実装した。model_design.md): 職能の一覧と責務はコードに固定し、調整できる部分
  (性格づけ・追加の指示等)だけをデータで持つ。生成AIの設定は、当面プロジェクトの設定(文章生成・音声合成)を全員で共有する。
  職能ごとの上書きは、必要になったら拡張する。
  - Researcher: 準備の項目1・2の資料を索引にし、他のエージェントの問いに根拠を出典付きで返す。考証(プロット・台詞と資料の
    食い違いの確認)も担う。作品は書き換えない。
  - CastingDirector: 準備の項目4(人物と声の対応付け)。提供元ごとの声の一覧の知識はここに閉じ込める。
  - Actor: 資料のVoice Actor。Castingごとに1つで、台詞と演出を受け取り音声合成で音声を作る(人物を演じる生成AIではない)。
- 作品のモデル(2026-09-30ユーザー決定):
  - **Drama=Project**(2026-09-30ユーザー決定)。QIDMに準じて集約の根はProjectとし、QIDMのDomainに相当する階層を
    **Dramaturgy**とする(下の「Dramaturgy」)。
  - **階層は「作品全体を包括するドラマツルギー(Dramaturgy) → 幕(Act) → シーン」。** この階層を上下しながら情報を得たり、
    双方向に書き換えたりすることがある。そのため、各階層があらすじ(シーンのあらすじ・幕のメタストーリー・作品全体の
    メタメタストーリー)を保持できるようにする。双方向の書き換えの仕組みは、かなり将来の構想なので保留。
  - Actは`input_language`・`output_language`を設定できる。
  - Characterの**経歴と人物関係はクラスとして定義する**(自由記述にしない)。
    - **経歴はハルシネーション対策として極めて重要**(ユーザーの経験から)。
    - 経歴の時期は3種類すべて持つ: 言葉としての時期(例: 中学校時代)・日付や年代・順番。**必須は順番だけ**。
    - **時間の順序は1次元ではなく、位相(Temporal Topology)として扱う。** 叩き台: Period(点。言葉としての時期・
      日付や年代はどちらも任意)と、Periodどうしの関係(前後・接する・重なる・含む・同時等。Allenの区間代数に相当)。
      「順番は必須」は「**どのPeriodも、ほかのPeriodとの関係を少なくとも1つ持つ**」と読み替える(2026-09-30ユーザー決定)。
    - Sceneは、描く時期として別にPeriodを参照する(暫定。回想等で語りの順と描く時期が違うため。実際に生じる問題はまだ見えない)。
    - 時間の分岐(並行世界・もしもの筋)は、可能性としてはありえるが保留。
    - 人物関係(Relationship)はPeriodを持てる(同じ2人の関係が時期によって変わる)。
    - 経歴は自由記述のエピソードだけでなく、人間関係も持つ。
    - **物語に直接出てこない人物もCharacterとして設定し**、人物関係を定義するクラスでつなぐ(声の割り当てが無い人物になる)。
  - **台詞とSceneは絶対に分離する。** 生成AIには、聴衆が満足する品質のSceneを直接作る能力が無いため、台詞の段階を
    独立させる(台詞の段階を「演出が空のDialogue」で表す案は却下)。
  - 効果音・環境音・BGMはそれぞれクラスとして設計する。当面は空のクラスでよい。
  - **翻訳はSceneの段階と音声の生成の間に置く**(Actの`input_language`→`output_language`)。
    翻訳の職能(Translator)は置かない(ユーザー)。
- 組み立てた設計: [model_design.md](model_design.md)(2026-09-30。細部は暫定で置き、基本の部分を動かしてから見直す)。
- 2026-09-30、ユーザーがUMLクラス図で再整理した(正本。[model_design.md](model_design.md))。上の経緯の名前との対応: Period→TemporalNode、
  TemporalRelation→TemporalEdge(Historyが束ねる)、Casting→Cast。`input_language`・`output_language`はActからDramaturgyへ移った。

## Projectの作り直し

- 決まったこと([architecture.md](architecture.md) 5節・7節、2026-10-01): 旧来の`Project`は削除した。`Project`はメタ情報と設定だけを持ち、
  作品モデルはDBの正本。`ModelDefinition`は`core/infra/io`のまま。
- 残り(GUIを開発しながら決める。2026-10-01ユーザー):
  - ディレクトリ構成: `drafts/`(下書きはDBに入れたので未使用)、制作の出力(`work/`・`sound/`)、実験用の`<root_dir>/model/`(モデル定義YAMLの複製。
    DBが正本になったので、取り込みの元としてだけ使う)。
  - 制作の流れの入出力(DBの正本から読み、生成の結果を下書きに反映する形。音声ファイルの参照)。
  - エージェント(演者の声`voice_name`)の置き場所。
  - 生成AIの設定: `main.py`に直書きの`system_instruction`・`TextConfig`の置き場所。
  - レジストリと`project_id`(公開APIはレジストリ、`main.py`はディレクトリを直接受け取る)、Datasetと作品の結び付け、
    `project.yaml`の`server.base_url`・`paths`の要否、別名で保存の扱い、`core/project/project.py`の`dataclass`を素のクラスにするか。

## Dramaturgy(QIDMのDomainに相当する階層)

- QIDMのDomainに相当する階層はDramaturgy(2026-09-30ユーザー決定。2026-09-29の「Dramaに置き換える」案を改めた。
  Drama=Project)。名前ではなく題を持つ想定(現状のコードは`drama_title`)。
- Datasetのメタデータと台帳は、仮に`drama_id`・`drama_title`を持つ(現状は常に未割当。名前はDramaturgyの定義に合わせて
  直す)。Dramaturgyの定義ができたら、QIDMにあった次の機能を戻すか決める: DatasetをDramaturgyに割り当てる、
  DramaturgyごとのDatasetの一覧と保存(CSV)。
  QIDMの`domain_version`(Domainの版の管理)は持ち込んでいない。
- `DatasetCategory`は`unspecified`・`reference`だけにした(QIDMの`raw_data`・`correlation_comparison`は、Domainと分析の概念のため削除)。

## Dataset・drafts/

- 必要。現状はQIDMの`Dataset`(datasets/配下の本体とサイドカーのデータメタデータYAML、台帳)をそのまま持ち込んでいる。
  何を置くか(参考資料・生成の途中結果等)は未決定。

## 対話方式の制作(保留。パッケージの移行が終わってから)

- エージェントどうしのやり取り(発注・提案と反映・利用者との相談)は、エージェントのモデル(`core/model/agent/`)ではなく、
  公開API・処理の側で設計する(2026-09-30ユーザーの指摘。当初`core/model/agent/`に置いた`Task`・`Proposal`・`Conversation`は削除した)。

- 現状は各工程を生成AIへの1回の依頼(ワンショット)で行っている。次の段階で対話方式にする予定。
- QIDMのdrafts(`drafts/<id>/`に作成途中の成果物・会話・版の履歴を置き、ステップごとに提案をApply/Undoする。
  [qidm_reuse.md](qidm_reuse.md) C群)の枠組みを、先に置いておいてもよい。

## SQLite

- 作品モデルのDBは決まり、実装した([architecture.md](architecture.md) 7節・[database_design.md](database_design.md)、2026-10-01)。
- エージェントは作品が所有し、DBに入れた(2026-10-01)。未定: Datasetの台帳との関係。下書きの根拠・会話と、提案の形
  (今はApplyも下書きの中身を作品モデル全体で置き換える。対話方式の制作で設計)。版から下書きを作る(過去の版に戻す)か。
- 暫定で、プロジェクトに`project.db`を置き、Datasetの台帳(`dataset_registry`)だけを持たせている(QIDMではdomain.dbの中)。
  作品モデルのテーブルも`project.db`に置いた。

## ドラマの構成要素の再定義(`core/model/`)

- 人物(character)と声・演者(actor)の区別、場面(scene)・台詞(transcript)・演出(DirectorNotes)の構造。
- 提供元に依存する声の一覧(`GeminiVoice`)と音声タグ(`AudioTag`)の置き場所。
- 翻訳(サンプルの`scene_000_ch.yaml`は中国語)を工程として扱うか。

## エージェントの将来構想(2026-10-02ユーザー)

- **利用者が自分で新しいエージェントを定義し、生成AIでそのエージェントと相談できる**ようにする構想。面白いがスコープの外なので保留。
  今はエージェントは職能ごとに決まっていて(システム既定)、利用者は足さない。
- **Actor(演者)の設定の置き場所**: Agentsタブではなく別の場所がよい(ユーザー)。配役(CastingDirectorの仕事)と合わせて検討する。保留。

