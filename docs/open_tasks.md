# 残タスク

## 現状を大きく変えずに、適切なパッケージへ切り分ける

方針: 制作の流れと動作は変えず、置き場所と重複だけを整理する。移動先はユーザーと確認してから行う。

- [x] `main.py`のAPIキーの直書きを消す
- [x] プロンプトの部品を`core/genai/prompt.py`に一本化し、`core/model/prompt.py`を削除する
- [x] `core/prompts.py` → `core/prompt/drama_production/`
- [x] `core/function.py` → `core/service/process/production/`
- [x] `core/utils.py`(未使用の`AudioUtility`)を削除する
- [x] QIDMの骨組みに残るQIDM固有の記述を消す(DomainはDramaへ仮に置き換え)
- [x] [qidm_reuse.md](qidm_reuse.md) のA群と、それが依存するB群を持ち込む
- [x] `requirements/`(base・api・dev・rag-ja)と`pyproject.toml`
- [x] CLAUDE.mdの構成表・厳守ルールをAIDCに合わせて書き直す

## 次に行うこと

- [x] `.venv`に`requirements/dev.txt`を入れる
- [ ] 参考資料のサンプル(PDF・DOCX)を用意する。無いとRAGのテスト3件がskipになる
  (`tests/reference_samples/`か環境変数`AIDC_REFERENCE_SAMPLE_DIR`。第三者の論文はリポジトリに入れない)

## 設計(future_design.mdの項目)

- [x] `core/model/`の作品・エージェントのクラスと属性([model_design.md](model_design.md)、2026-09-30)
- [ ] 各クラスの機能(メソッド)の定義
- [x] モデル定義YAML(`apps/sample_data`)から制作の流れを実行する(仲介`_model_definition_project.py`、`plot_001`で完走、2026-09-30)
- [ ] 演じ方(`Cast.performance`)を入れた音声での完走チェックと、残りの4シーン(`plot_002`〜`plot_005`)。`Project/TEST_PROJECT_03`を使う(生成AIの課金を伴うので、実行前にユーザーに確認)
- [ ] 制作の流れで、原稿をモデル定義YAML(`scenes/`)に書き戻す(旧来の`context`は`Situation`へ。今は旧来の形の作業ファイル)
- [ ] 制作の流れを新しいモデルへ移し、`core/schema/formats/_legacy_drama.py`を削除する(`_legacy_project.py`は2026-10-01に削除)
- [ ] Projectの作り直しの残り(GUIを開発しながら決める。[future_design.md](future_design.md)「Projectの作り直し」)
- [x] 作品モデル(`core/model/drama`)のDB: 正本・版・下書き([database_design.md](database_design.md)、2026-10-01)
- [x] 作品モデルのDBを公開API(`drama_model`・`drama_draft`)から使えるようにする(2026-10-01)
- [ ] 制作の流れ(main.py)を、モデル定義YAMLのファイルではなくDBの正本から読むようにする
- [x] エージェントの再設計(`BaseAgent`・`AgentTask`、作品が所有、DB・YAML・Agentsタブ。2026-10-01)
- [x] エージェントの既定の2段(システム既定`core/default/agents/`・プロジェクトのユーザー既定)と、Agentsタブの既定の読み込み(2026-10-02)
- [ ] システム既定の文面(役割・厳守事項・禁止事項・タスク)の見直し(暫定。ユーザー)
- [ ] 作品があるプロジェクトへの取り込みで`key`が衝突する([known_issues.md](known_issues.md))
- [ ] エージェントの情報からSystemを組み立てる`core/prompt`の共通の部品と、生成AIを呼ぶ処理(`service/process`)。制作の流れのプロンプトをそこへ移すか
- [ ] SQLiteの残り: Datasetの台帳と作品の結び付け
- [x] Web GUIの枠(`apps/AIDC-Console`: メニューバー・Tree・パネル、Project Overview・Data Viewer。2026-10-01)
- [x] GUI: EditメニューとDramaturgy Editor(Properties・Acts)、Treeの作品の一覧(2026-10-01)
- [ ] GUI: Dramaturgy Editorに人物・場所・シーン等のタブを足す。Treeに作品の中(Act→Scene等)を並べるか(ユーザーと相談)
- [x] 文章生成の設定を作品作り用(`creative_llm`)と作業補助用(`assistive_llm`)に分ける(2026-10-02)
- [x] GUI: 人物パネル(Characters・Groups・Relationships。プロジェクト全体)と企画書の登場人物の取り込み(2026-10-02)。[architecture.md](architecture.md) 9節
- [ ] 企画書の取り込みの矛盾の理由の保存・再確認(仕組みは保留)
- [ ] 新しい声の一覧の識別子(例: `ja-jp-advisor-1`)で音声合成できるかを、実際に1回呼んで確かめる(課金を伴うのでユーザーに確認してから)。
  [architecture.md](architecture.md) 9節
- [x] 企画書のモデル(`Proposal`)とモデル定義YAML、Dramaturgy EditorのProposalタブ(2026-10-01)
- [x] GUI: Build with AI(生成AIと相談しながら作るパネル。Proposalの工程、対話とワンショット下書き。2026-10-02)
- [x] Build with AIを本物の生成AIで確かめる(Gemma`gemma-4-31b-it`で、ワンショット・対話・質問。1回に約50秒。2026-10-02)
- [ ] Build with AI: 利用者が「提案だけ聞かせて」と言っても、生成AIが企画書の変更を提案(proposal)してしまう(Applyしなければ入らないので実害は無い)。
  指示を直すか(ユーザーと相談)
- [x] Build with AIの人物の工程(Characters・Groups・Relationships。2026-10-02)
- [x] Build with AIのSynopsisの工程(作品全体と幕のあらすじ。2026-10-05)
- [x] Build with AIのScenesの工程(シーンの題・あらすじ。2026-10-05)
- [x] Build with AIのScriptの工程(読み上げ台本。1シーンずつ台詞を書く。2026-10-05)
- [x] Build with AIのDirectionの工程(演出付きの原稿・訳文。1シーンずつ。2026-10-05)
- [ ] Build with AIのSynopsis・Scenes・Script・Directionを本物の生成AIで確かめる(課金を伴うのでユーザーに確認してから)
- [x] 作品のモデルの演出付きの原稿から音声を作る処理(Dramaturgy EditorのRecordingタブ。2026-10-05)
- [ ] Recordingタブを本物の音声合成で確かめる(新しい声の一覧の識別子で読めるか、感情タグ・演出の効き方、訳文の読み上げ。課金を伴うのでユーザーに確認してから)
- [x] Dramaturgy EditorのScenesタブで台詞の編集と訳文の作成(Plot・Script・Translation。2026-10-05)
- [ ] 訳文を作る担当の整理: Build with AIのDirectionの工程はDirector(`direct_scene`)が演出と一緒に訳文も作るが、設計
  (model_design.md)では翻訳はStageManagerの`translate`。Directionの訳文をやめてTranslationに任せるか(ユーザーと相談)
- [ ] `main.py`の音声の生成を、Recordingと同じ処理(`scene_recorder`)に移すか(旧来の`work/scene/`の原稿をやめるか。要相談)
- [ ] Build with AIの工程を足す(効果音・環境音・BGM等。モデルの属性から)
- [x] 企画書のYAMLの読み込み(ProposalタブのImport from YAML。フォームに入れ、Saveで下書きへ。2026-10-01)
- [ ] GUI: 準備の5項目(future_design.md「GUIで扱う制作の準備」)
- [ ] GUIの検証の手順(QIDMの`.claude/skills/qidm-browser-verify/`を持ち込むか)
- [ ] CLIの要否、`main.py`の扱い(保留)
- [ ] 対話方式の制作(保留。パッケージの移行が終わってから)
