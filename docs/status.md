# 実装済みの範囲

2026-09-29時点。旧`lib/`を`core/`へ移し、別プロジェクト(QIDM)の構成に寄せてパッケージを切り分けている途中。

## 動くもの

`main.py`(ローカルでのスクリプト実行)による制作の流れ。`.venv/bin/python main.py <root_dir> [開始する工程] [--plot 名前]`。
`plot/`のあらすじを名前順に並べ、n番目(0から)を`script_nnn.txt`・`scene_nnn.yaml`・`scene_nnn.mp3`に対応させる。
各工程の直後に、出力が次の工程に引き継げるかを検査し(台詞の形式と話者、原稿のYAMLの構造・`scene_id`・記入欄の残り・
`Scene`への組み立て、音声の長さと無音)、合格すれば次へ進み、不合格ならそこで止める(終了コード1)。
開始する工程は`dialogue`(既定)・`scene`・`sound`、検査のみは`check-dialogue`・`check-scene`・`check-sound`。

| 工程 | 関数 | 入力 → 出力 |
| --- | --- | --- |
| 台詞の生成 | `core/service/process/production/dialogue_generator.py` | `plot/*.txt`+`character/*.txt` → `script/*.txt` |
| 原稿の生成 | `core/service/process/production/scene_generator.py` | `script/*.txt` → `scene/*.yaml`(`scene_id`はシステムが付ける) |
| 音声の生成 | `core/service/process/production/sound_generator.py` | `scene/*.yaml`+`actor/*.yaml` → `sound/*.mp3`(pydubで連結。ffmpegが必要) |

- 各工程はワンショット(生成AIへの1回の依頼)。プロンプトは`core/prompt/drama_production/`(`dialogue`・`scene`・`sound`)。
- 生成AIは`core/genai`の`create_text_generator`/`create_speech_generator`(Gemini)を使う。APIキーは`~/.aidc/secrets.env`の
  `AIDC_GEMINI_API_KEY`(`generator_builder.saved_api_key`。無ければ未設定の旨で止まる)。
- `main.py`が見るのは`<root_dir>/project/`([known_issues.md](known_issues.md))か、`<root_dir>/model/`(モデル定義YAML)。
  `apps/sample_project/`・`apps/sample_data/`を指定すると断る。
  2026-09-29、`plot_001.txt`で音声まで通すための実験用のプロジェクトは`Project/TEST_PROJECT_01`。
- モデル定義YAMLからの実行(2026-09-30): `<root_dir>/model/`に`apps/sample_data`を複製して使う。仲介は
  `core/service/process/production/_model_definition_project.py`(暫定。現行の工程が使う`Project`と同じ入口をモデルから用意する)。
  人物設定は配役のある人物(話者)の`Character`から文章にし(`core/prompt/drama_production/dialogue.py`の`character_profile`)、
  話者名はフルネーム(照合では空白を無視)。台詞は`model/scripts/`に書き戻し、原稿は`work/scene/`(旧来の形。`Dialogue`に`context`が
  無いため)、音声は`sound/`。2026-09-30、`Project/TEST_PROJECT_02`で`plot_001`を音声まで完走した(台詞12行、音声103.6秒)。

## 作品とエージェントのモデル(クラスと属性のみ、2026-09-30)

- `core/model/drama/`(作品)と`core/model/agent/`(参加者)に、[model_design.md](model_design.md)のクラスと属性を定義した。
  構成はユーザーの承認前(レビュー中)。機能(メソッド)はまだ無い。制作の流れ(main.py)からはまだ使っていない。
- `core/model/`は純粋なモデルだけにした。現行の制作の流れが使うものは外へ移した: 旧`core/model/drama.py`→`core/schema/formats/_legacy_drama.py`、
  旧`core/model/project.py`→`core/service/process/production/_legacy_project.py`。空の`core/model/factory.py`は削除した。
- モデル定義YAML(作品の側): `core/model/drama/factory.py`(`build_*`)・`core/schema/formats/dramaturgy_definition.py`・
  `core/infra/io/model_definition_reader.py`・`model_definition_writer.py`。1ファイルでも分割した複数のファイル(シーンごとのプロット・台詞・原稿も別のファイル)でも読み書きでき、
  識別子を保って往復できる(2026-09-30。形はレビュー前。[model_design.md](model_design.md))。テストは`tests/core/test_model_definition_io.py`。
  公開API・制作の流れからはまだ使っていない。
- `apps/sample_data/`: `apps/sample_project/`の人物・プロット・配役(`actor/actors.yaml`)を分割方式のモデル定義YAMLに変換したもの
  (2026-09-30。場所・台詞・原稿は空の骨組み。変換で見つかった構造上の問題は[model_design.md](model_design.md)「サンプルデータ」)。

## 実装済みだが、まだ制作の流れ(main.py)から使っていないもの(QIDMから持ち込み、2026-09-29)

- `core/genai/`: 文章生成(Gemini・OpenAI互換サーバー)、構造化出力、埋め込み、モデル一覧・接続先の候補の取得、
  出力の疑わしい文字の判定(`character_check`)、資料の検索(`rag/`: PDF・DOCX・XLSX・CSVのテキスト化・分割・
  BM25と埋め込みの併用)。
- プロジェクト(暫定の形。[future_design.md](future_design.md)「Projectの作り直し」):
  - `core/project/`: `Project`(project.yaml)・`ProjectLayout`(`project.yaml`・`project.db`・`datasets/`・`drafts/`)・`Dataset`
  - `core/infra/store/`: project.yamlの読み書き・プロジェクトのレジストリ(`~/.aidc/projects.yaml`)・
    APIキー(`~/.aidc/secrets.env`、名前は`AIDC_<提供元>[_<接続先>]_API_KEY`)・Datasetのファイルと台帳(`project.db`の`dataset_registry`)
  - `core/service/process/edit/`: プロジェクトの作成・更新、生成AIの設定の更新、Datasetの保存・改名・削除とメタデータ
  - `core/service/process/genai/`: Projectの設定と保存済みのキーからの生成器の組み立て、接続確認、設定の入力補助、参考資料の検索
- 公開API・HTTP(`core/service/api`・`core/schema/api`・`api/routers`):
  - `project`: 作成・開く・一覧・プロパティ・保存・別名で保存
  - `preference`: 生成AIの設定・APIキー・接続確認・モデル一覧・接続先の候補
  - `dataset`: 一覧・PDF/DOCX/XLSXの追加・中身とファイルの取得・メタデータの参照と更新・削除。
    ドラマへの割り当ては無い(常に未割当。[future_design.md](future_design.md)「Drama」)
- テスト(`tests/`、`.venv/bin/python -m pytest`): 102件が通り、3件がskip(2026-09-30)。skipは参考資料のサンプルが無いため([open_tasks.md](open_tasks.md))。
