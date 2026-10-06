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
- `main.py`が見るのは`<root_dir>/model/`(モデル定義YAML)だけ(旧来のテキストのファイルの形は2026-10-01に削除)。`apps/sample_data/`を指定すると断る。
- モデル定義YAMLからの実行(2026-09-30): `apps/sample_data/令和但馬道中膝栗毛`の`drama/`・`agent/`を`<root_dir>/model/`に、`project.yaml`を`<root_dir>/`に複製して使う。仲介は
  `core/service/process/production/_model_definition_project.py`(暫定。現行の工程が使う`Project`と同じ入口をモデルから用意する)。
  人物設定は配役のある人物(話者)の`Character`から文章にし(`core/prompt/drama_production/dialogue.py`の`character_profile`)、
  話者名はフルネーム(照合では空白を無視)。台詞は`model/scripts/`に書き戻し、原稿は`work/scene/`(旧来の形。`Dialogue`に`context`が
  無いため)、音声は`sound/`。2026-09-30、`Project/TEST_PROJECT_02`で`plot_001`を音声まで完走した(台詞12行、音声103.6秒)。
  2026-10-01から、話者は演者(`Actor`)のいる配役の人物で、声は演者、演じ方は`Cast.performance`(音声合成への指示のAUDIO PROFILE)、
  生成AIは`<root_dir>/project.yaml`の`genai`(無ければ既定)。`Project/TEST_PROJECT_03`(新しい`apps/sample_data`+`project.yaml`)で、
  `TEST_PROJECT_02`の台詞・原稿・音声に対する検査が通ることを確かめた(生成AIは呼んでいない。音声は演じ方を入れる前のもの)。

## 作品とエージェントのモデル(クラスと属性のみ、2026-09-30)

- `core/model/drama/`(作品)と`core/model/agent/`(参加者)に、[model_design.md](model_design.md)のクラスと属性を定義した。
  構成は2026-10-01にユーザーが承認した。機能(メソッド)はまだ無い。制作の流れ(main.py)からはまだ使っていない。
- `core/model/`は純粋なモデルだけにした。現行の制作の流れが使うものは外へ移した: 旧`core/model/drama.py`→`core/schema/formats/_legacy_drama.py`、
  旧`core/model/project.py`は旧来の`Project`として移した後、2026-10-01に削除した。空の`core/model/factory.py`は削除した。
- モデル定義YAML(作品の側): `core/model/drama/factory.py`(`build_*`)・`core/schema/formats/dramaturgy_definition.py`・
  `core/infra/io/model_definition_reader.py`・`model_definition_writer.py`。1ファイルでも分割した複数のファイル(シーンごとのプロット・台詞・原稿も別のファイル)でも読み書きでき、
  識別子を保って往復できる(2026-09-30。形は2026-10-01承認。[model_design.md](model_design.md))。テストは`tests/core/test_model_definition_io.py`。
  公開API・制作の流れからはまだ使っていない。
- `apps/sample_data/`: 作品ごとのディレクトリに分けた(2026-10-01ユーザー)。`令和但馬道中膝栗毛/`はサンプルの人物・プロット・配役を分割方式のモデル定義YAMLにしたもの(旧来のサンプル`apps/sample_project`から変換。元は2026-10-01に削除)。`ハチ北スキー場ガイド/`は企画書(`proposal`)だけを持つ作品(2026-10-01、ユーザー提供の企画書のテキストから)。同じディレクトリの`ハチ北スキー場.kml`は場所の雛形の形に整理した地図(2026-10-02。ユーザー提供のKMLとリフト施設概要表から。2026-10-02にユーザーがGoogle マイマップでLocation 2つとSiteFlow 7本を描き足した。Location 11・SiteFlow 7(`direction`は空)・補助情報)
  (2026-09-30、10-01。作品は`drama/`、エージェント(演者)は`agent/`。直下の`project.yaml`はプロジェクトの見本(モデル定義ではない)。場所・台詞・原稿は空の骨組み。変換で見つかった構造上の問題は
  [model_design.md](model_design.md)「サンプルデータ」)。
- 人物・人物関係は作品の外(持ち主はProject。今は読み込み結果`ModelDefinition`の`characters`・`relationships`に仮置き)。作品は参照で持つ(2026-10-01)。
- モデル定義YAMLの識別子と参照(2026-10-01): すべてのエンティティが`id`と`key`を持ち、参照は`{ref: key}`。書き出しは`key`を種類と通し番号で振る。
- エージェント(2026-10-01改訂): 抽象クラス`BaseAgent`と`AgentTask`(役割・性格づけ・厳守事項・禁止事項・タスク。既定は職能のクラス)。
  Producerは削除。作品が所有し(`Dramaturgy.agents`)、モデル定義YAMLは`dramaturgy.agents:`に職能ごと(`actors`は`cast`・`voice_name`も。
  分割では`agents.yaml`)。DBは`agent`・`agent_task`のテーブル。省略した項目は職能の既定、書き出しは全文。
- エージェントの既定(2026-10-02): システム既定`core/default/agents/<職能>.yaml`(正本。7職能)と、プロジェクトのユーザー既定
  `<プロジェクト>/user_default/agents/<職能>.yaml`(Actor以外の6職能。作成時に複製、無ければ使うときに複製)。職能のクラスは既定の文面を
  持たない。読み込みと補完は`core/infra/io/agent_default_reader.py`、ユーザー既定は`core/infra/store/agent_default_store.py`。
  公開API・HTTP`agent_default`(`GET /projects/{id}/agent-defaults`・`PUT .../agent-defaults/{職能}`・`POST .../agent-defaults/{職能}/restore`)。

## 企画書(`Proposal`、2026-10-01)

- `core/model/drama/proposal.py`の`Proposal`(企画書)・`ProposalCharacter`(企画書の登場人物)。`Dramaturgy.proposal`(作品に1つ)。
  モデル定義YAMLは`dramaturgy.proposal`、DBは`proposal`・`proposal_character`のテーブル、部分YAMLでは`proposal.characters`を丸ごと置き換える。
- 企画書のYAMLは、Dramaturgy EditorのProposalタブの`Import from YAML`でフォームに読み込める(2026-10-01)。

## 作品モデルのDB(2026-10-01)

- `project.db`に、作品モデル(`core/model/drama`)の正本・版・下書きを置く([database_design.md](database_design.md))。
  正本は下書きの確定でだけ変わり、確定のたびに版が1つできる。下書きはApply・直接編集・取り込み・Undoの履歴を持つ。
- モデル定義YAMLに`dramaturgies:`(作品の一覧)を足し、プロジェクトの作品モデル全体を1つのYAMLで読み書きできる
  (`ModelDefinition.dramaturgies`・`temporal_nodes`・`locations`、`model_definition_to_yaml`)。`ModelDefinition.dramaturgy`は作品が1つのときだけ使える。
- 原稿の台詞の空の状況(`situation: {}`)を書き出しで省かないようにした(省略=シーンの状況と区別する)。
- `apps/sample_data/令和但馬道中膝栗毛/drama`を取り込んで確定し、正本から読み直した作品モデルが元と同じになることを確かめた(テスト)。
- 部分YAMLの重ね合わせ(2026-10-01): Apply・直接編集・取り込みは、変えたい部分だけのモデル定義YAMLを下書きに重ねる
  (`core/infra/io/model_definition_patch.py`。規則は[database_design.md](database_design.md))。取り込みは`replace`で全体を置き換えられる。
- 公開API・HTTP(2026-10-01): `drama_model`(正本・版の一覧・版の写し。読むだけ)と`drama_draft`(下書きの作成・一覧・中身・履歴・
  取り込み(本文・サーバーの手元のパス)・Apply・直接編集・Undo・確定・破棄)。エンドポイントは[database_design.md](database_design.md)。
- 制作の流れ(main.py)からはまだ使っていない。

## Web GUI(AIDC Console、2026-10-01)

- 場所と移動(2026-10-02): `Location.geometry`(WKT)と`SiteFlow`(場所の間の移動)、作品の`locations`・`site_flows`(参照)。
  project.dbはGeoPackageとしても読め、`location`・`site_flow`をQGIS・GDALで開ける(テストでogrinfoから確かめる)。
  Dramaturgy EditorにLocations(場所の編集・移動の向き・Generate Scenes)とScenes(シーンの一覧・編集・追加・削除)のタブ。
  テストは`tests/core/test_site_flow.py`。ハチ北のサンプルは`drama/locations.yaml`(Location 11・SiteFlow 7)を作品が参照する。
- 配役と声(2026-10-02): `Cast.billing`(主役・脇役・端役)、`Actor`の`tts_provider`・`tts_model`、声の一覧(`core/genai`の
  `SpeechGenerator.list_voices`、`GET /projects/{id}/voices`)。Dramaturgy EditorのCastsタブ(配役・演じ方・声の条件・演者の声)と、
  Build with AIのCasting(`cast_character`)・Audition(`assign_voice`)の工程。テストは`tests/api/test_ai_build_casting.py`・`tests/core/test_cast_actor.py`。
- 場所の地図の取り込み(2026-10-02): KML・KMZ・GeoPackageを作品ごとに取り込む(LocationsタブのImport KML / GeoPackage...、
  `POST .../drama-drafts/{draft_id}/import-geodata`)。補助情報は作品に割り当てたDataset(GeoPackage)になる。書き出しはまだ無い。
  テストは`tests/api/test_geodata_import.py`・`tests/core/test_geodata_reader.py`。
- 地図の上での場所の編集(2026-10-02): Edit > Edit Location on Map(`apps/AIDC-Console/static/location_map_panel.js`。Leaflet 1.9.4・
  Leaflet-Geoman(無料版)2.20.2を`static/vendor/`にベンダリング。背景は地理院タイル(標準・淡色・写真)とOpenStreetMap)。面を描くとLocation、
  線を描くとSiteFlow(頂点をクリックして描く)、形の編集・移動・削除、属性の入力、移動の向きの矢印、形の無い場所への面の描き足し(Draw Shape)。
  補助情報のDatasetは表示だけ。保存は`GET`・`POST .../drama-drafts/{draft_id}/map`(地図の取り込みと同じ規則で下書きに入る)。
  テストは`tests/api/test_location_map.py`(画面はPlaywrightで確かめた。自動テストは無い)。
- GISの汎用ライブラリ`core/gis/`(2026-10-02): `core/infra/io`の`geometry_wkt.py`・`geopackage.py`と、`geodata_reader.py`のKMLの読み取りを移し、
  GeoJSONとの変換と点を含む面の判定を足した。テストは`tests/core/test_gis_geometry.py`・`tests/core/test_gis_independence.py`。
- 場所の雛形(2026-10-02): `apps/AIDC-Console/templates/location_template.kml`・`location_template.gpkg`(Location=面・SiteFlow=線・それ以外=補助情報。
  説明は同じディレクトリの`README.md`、設計は[future_design.md](future_design.md)「LocationとSiteFlow」)。作品モデル・project.dbへの組み込みと取り込みは下の項目。

- `apps/AIDC-Console/`(ビルド不要の素のHTML/CSS/JS)。APIサーバーが`/app/`で配信する(`scripts/server/start.sh`の後に
  `http://127.0.0.1:8100/app/`。`/`は`/app/`へ転送する)。QIDM Consoleの共通部分を複製して直したもの([qidm_reuse.md](qidm_reuse.md))。
- 画面: 上にメニューバー(`Project`・`Edit`・`Connection`)、左にTree、右にパネルの入れ物(main-area)。QIDMにあったPropertiesの区画は置かない。
- メニュー: Project(作成・開く・保存・別名で保存・閉じる・Preferences・Exit)、Edit(New Dramaturgy・Dramaturgy Editor・Edit Location on Map・Character Editor・Build with AI)、
  Connection(接続・接続テスト・パスの更新・切断)。
- Tree: `Project`(Project Overviewを開く)・`Dramaturgies`(正本の作品の一覧。選ぶとDramaturgy Editor)・`Datasets`
  (Datasetの一覧。選ぶとData Viewer)。作品の中(Act→Scene・人物等)の並びはまだ無い。
- Dramaturgy Editor(`dramaturgy_editor_panel.js`、2026-10-01): Propertiesタブ(題・あらすじ・入力/出力の言語・作品の削除)と
  Actsタブ(幕の一覧と題・あらすじ。追加・削除、削除すると残りのorderを詰める)。New Dramaturgyは題・幕数・言語から作品を作って確定する。
  保存の仕組みは[architecture.md](architecture.md) 8節。
  Proposalタブ(企画書。題・キャッチコピー・ログライン・企画意図・対象地域・あらすじ・登場人物(名前と説明の行を追加・削除))も置いた。
  Agentsタブ(2026-10-02改訂): 作品のエージェント(Actor以外)の一覧と、名前・役割・性格づけ・厳守事項・禁止事項・タスクごとの文面の編集。
  足りない職能はタブを開いたときにユーザー既定から読み込む。Reset to Default・Save as User Default・Restore System Default。
  New Dramaturgyはユーザー既定の6職能を必ず入れる。
  Proposalタブの`Import from YAML`は、企画書のYAML(最上位の`proposal:`か、モデル定義YAMLの`dramaturgy.proposal`)をフォームに読み込む
  (下書きにはSaveで入る。知らない項目があれば断る)。
- パネル: Project Overview(Overview・Summary・Generative AI・Datasetのタブ。Datasetの追加はPDF・DOCX・XLSXだけ)、
  Data Viewer(CSVは表、PDFはブラウザの表示、DOCX・XLSXはダウンロード)。
- 人物パネル(`character_editor_panel.js`、Edit > Character Editor、2026-10-02): プロジェクトの人物・まとまり・人物関係を編集する
  (Characters・Groups・Relationshipsのタブ。作品を選ばなくても開ける。名前だけで登録できる。使われている人物・人物関係は削除せず、使われている所を示す。
  経歴・人物関係の時期は、下書きにある時期から選ぶだけ)。Dramaturgy Editorと同じ編集用の下書き(`editor_draft.js`に共通化)を通し、Save Versionで確定する。
  CharactersタブのImport from Proposalで、作品を選んで企画書の登場人物を取り込む(名前が同じなら同じ人物。未登録はImport=骨組みから登録、
  登録済みはCheck=矛盾の確認→Cancel・Merge・Replace、矛盾が無ければAdd to Dramaturgy。取り込んだ人物は作品の登場人物の参照にも加わる)。
  生成AIはScriptwriterのタスク`import_proposal_character`・`check_character_conflict`(作業補助)。処理は`core/service/process/genai/character_importer.py`、
  プロンプトは`core/prompt/character_import.py`、APIは`POST /projects/{id}/drama-drafts/{draft_id}/character-import`(と`/check`)。矛盾の理由は今は保存しない。
  headless Chromeで、手元のllama.cpp(Gemma 4 26B-A4B)による取り込み・矛盾の確認・キャンセル、名前だけの人物の追加、同名の拒否、まとまり・人物関係の表示、
  使われている人物関係の削除の拒否、Save Versionを確かめた(手元の生成AIでは1回に約3分かかった。[known_issues.md](known_issues.md))。
- Build with AI(`ai_build_panel.js`、Edit > Build with AI...、2026-10-02): 生成AIと相談しながら作品を作るパネル([architecture.md](architecture.md) 10節)。
  左に参照する資料・チャット(Dialogue/One-shot Draft)、右に工程のタブ(Proposal・Characters・Groups・Relationships・Synopsis・Scenes・Casting・Audition・Script・Direction)と
  その内容(企画書のフォーム、人物パネル・Dramaturgy Editorの該当タブを埋め込んだもの)。人物の工程(2026-10-02)は追加と更新だけで削除しない。
  Gemma(`gemma-4-31b-it`)で、企画書から人物4人・まとまり・向きのある関係6つを作れることを確かめた(約90秒)。
  提案は会話の中に変わる項目を出し、Apply・Undo。Clear・Save Version。会話は作品ごとに保存し、パネルを開き直すと続きから。
  処理は`core/service/process/genai/ai_builder.py`、プロンプトは`core/prompt/ai_build/`、会話は`core/infra/store/ai_build_store.py`、
  APIは`ai_build`(`GET /projects/{id}/ai-build/steps`、`GET|POST|DELETE .../ai-build/{工程}/messages`、`POST .../ai-build/messages/{id}/apply|undo`)。
  企画書のフォームはDramaturgy Editorと共通(`proposal_form.js`)。headless Chromeで、生成AIを決まった応答に差し替えたサーバーにより、
  対話・ワンショット・Apply・Undo・フォームの直接の保存・Save Version・開き直し・Clearを確かめた。
- Build with AIのSynopsisの工程(2026-10-05): Scriptwriterの`write_synopsis`で、作品全体のあらすじと、今ある幕の題・あらすじを書く
  (幕は番号で指し、増減しない。空の値では消さない)。右側はDramaturgy Editorの埋め込み専用のSynopsis([architecture.md](architecture.md) 10節)。
  テストは`tests/api/test_ai_build_synopsis.py`。headless Chromeで、生成AIを決まった応答に差し替えたサーバーにより、タブの切り替え・ワンショット・
  提案の表示・Apply(右側のフォームに反映)・フォームの直接の保存を確かめた。本物の生成AIではまだ確かめていない。
- Build with AIのScenesの工程(2026-10-05): Scriptwriterの`write_synopsis`で、今あるシーンの題・あらすじを書く(幕・シーンの番号で指し、増減しない。
  場所・時期・状況は変えない。空の値では消さない)。右側はDramaturgy Editorの埋め込み専用の`scene_synopsis`([architecture.md](architecture.md) 10節)。
  テストは`tests/api/test_ai_build_scenes.py`。headless Chromeで、Synopsisと同じ手順を確かめた。本物の生成AIではまだ確かめていない。
- Build with AIのScriptの工程(読み上げ台本。2026-10-05): Scriptwriterの`write_dialogue`で、選んだ1シーンの台詞の全体を書く(話者は配役済みの人物だけ。
  演出付きの原稿があるシーン・配役の無い作品は断る)。会話はシーンごと(`ai_build_message.scene_id`、APIの`scene_id`)。右側はシーンの選択と、
  Dramaturgy Editorの埋め込み専用の`script`(行の話者・台詞の編集、追加・削除)。[architecture.md](architecture.md) 10節。
  テストは`tests/api/test_ai_build_script.py`。headless Chromeで、シーンの切り替え(会話も切り替わる)・ワンショット・配役の無い人物の除外・Apply・
  行の追加と削除の保存を確かめた。本物の生成AIではまだ確かめていない。
- Build with AIのDirectionの工程(演出付きの原稿。音声合成の直前。2026-10-05): Directorの`direct_scene`で、選んだシーンの台詞ごとに、音声にする文
  (感情タグ入り。文言は変えない)・ト書き・演出を作る(訳文は作らない。2026-10-06)。右側はDramaturgy Editorの埋め込み専用の`direction`
  (Clear Directionで原稿を消す)。[architecture.md](architecture.md) 10節。テストは`tests/api/test_ai_build_direction.py`。headless Chromeで、
  ワンショット・Apply・直接の保存・Clear Directionを確かめた。本物の生成AIではまだ確かめていない。
- Dramaturgy EditorのRecordingタブ(音声の生成。2026-10-05): 言語(制作の言語=音声にする文、既定の音声の言語・訳文のある言語=その言語の訳文)を選び、演出付きの原稿から
  シーンごとに1つのmp3を作る(Record・Record All・Stop、再生・ダウンロード)。足りないもののあるシーンは理由を示して断る。保存先は
  `<プロジェクト>/recordings/<作品のid>/<言語>/<シーンのid>.mp3`([architecture.md](architecture.md) 8節)。テストは`tests/api/test_recording.py`。
  headless Chromeで、音声合成を偽物に差し替えたサーバーにより、足りないものの表示・Record All・再生用のファイルの配信・言語の切り替えを確かめた。
  **本物の音声合成ではまだ確かめていない**。
- Dramaturgy EditorのScenesタブの詳細をPlot・Script・Translationに分けた(2026-10-05): Scriptは台詞の行の編集(消した行の原稿も消す。
  文言を変えた行は原稿と食い違うと示し、Recordingは断る)、Translationは原稿の訳文の編集と、生成AIによる訳(StageManagerの`translate`。
  欄に入れるだけで、Saveで下書きへ)。[architecture.md](architecture.md) 8節。テストは`tests/api/test_scene_translation.py`。headless Chromeで、
  台詞の変更・削除と食い違いの表示、Translate・Save、Recordingでの食い違いの表示を確かめた。本物の生成AIではまだ確かめていない。
- 作品の言語と多言語の訳文(2026-10-06): Input Language・Output Language(とNew Dramaturgy)を言語の一覧(`core/default/languages.yaml`、
  `GET /languages`)のプルダウンにした。原稿の台詞の訳文を言語ごとにいくつでも持てるようにした(`Dialogue.translations`、DBは
  `script_element_translation`)。ScenesタブのTranslationは言語を選んで訳す・直す(ほかの言語の訳文は残る)。Recordingは訳文のある言語を
  すべて選べる。Build with AIのDirectionは訳文を作らない。headless Chromeで、プルダウン・韓国語への翻訳と保存(中国語の訳文が残る)・
  Recordingの言語の一覧・Output Languageの保存・New Dramaturgyのダイアログを確かめた。
- 文章生成の既定をGemma(Gemini APIの`gemma-4-31b-it`)にした(2026-10-02): `apps/sample_data/project.yaml`の`creative_llm`・`assistive_llm`と、
  `main.py`の既定(project.yamlに設定が無いとき)。GUIで作った新しいプロジェクトには既定が無い(Generative AIタブで設定する)。
- 文章生成の設定の分離(2026-10-02): Generative AIタブで、作品作り(Creative LLM)と作業補助(Assistive LLM)を別々に設定する
  (`project.yaml`の`genai.creative_llm`・`assistive_llm`。タスクとの対応は`core/service/process/genai/llm_role.py`。[architecture.md](architecture.md) 2.1節)。
  headless Chromeで、Assistive LLMに手元のllama.cpp(`localhost:8080`)を選ぶ→URLの自動検出→モデル一覧→接続テスト→保存を確かめた。
- 2026-10-01、headless Chromeで、接続→作成→Overviewの各タブ→PDFの追加→Data Viewer→閉じる→開く(Open Recent)を確かめた。
  Dramaturgy Editorは、作品の作成→Properties・Actsの編集→Save Versionで版が増えること、未確定の変更があるときのNew Dramaturgyの拒否、
  作品の削除の確定、古い版を元にした編集用の下書きの作り直しを確かめた。

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
- テスト(`tests/`、`.venv/bin/python -m pytest`): 221件が通り、3件がskip(2026-10-02)。skipは参考資料のサンプルが無いため([open_tasks.md](open_tasks.md))。
