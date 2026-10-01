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
- [ ] SQLiteの残り: `agent`をDBに入れるか、Datasetの台帳と作品の結び付け
- [ ] インターフェース(保留。GUIはQIDMの`apps/QIDM`を参考にする。準備の5項目は future_design.md「GUIで扱う制作の準備」)
- [ ] 対話方式の制作(保留。パッケージの移行が終わってから)
