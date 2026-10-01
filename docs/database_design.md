# 作品モデルのDBの設計(`core/model/drama`)

2026-10-01にユーザーが承認し、実装した。方針は [architecture.md](architecture.md) 7節。
対象は`core/model/drama`だけ。属性はモデル([model_design.md](model_design.md))と1対1に対応させる。

## 実装

| 役割 | 場所 |
| --- | --- |
| ① 正本のテーブルの読み書き | `core/infra/store/drama_model_store.py`(`write_model`=すべて消して書き直す・`read_model`。接続を受け取りコミットしない) |
| ②③ 版と下書きのテーブルの読み書き | `core/infra/store/drama_version_store.py` |
| 下書きの手順 | `core/service/process/edit/drama_draft_editor.py`(`create_draft`・`import_definition`/`import_yaml`・`apply_to_draft`・`edit_draft`・`undo`・`confirm_draft`・`discard_draft`・`load_model`等。project.dbのパスを受け取る) |
| 写しの形 | モデル定義YAMLの`dramaturgies:`(`model_definition_writer.model_definition_to_yaml`)。読み込み結果`ModelDefinition`は作品の一覧(`dramaturgies`)と、所有者の無い時点・場所(`temporal_nodes`・`locations`)を持つ |
| テスト | `tests/core/test_drama_draft_editor.py` |

- 下書きの作成は、最新の版の写しを履歴の0行目(create)にする(版が無ければ空の作品モデル)。
- 写しは、渡されたYAMLを組み立て直してから書き出したもの。idの無い要素にはここでidが付き、以後の履歴・版・正本で同じidを保つ。

## 部分YAMLの重ね合わせ(2026-10-01ユーザー承認。問題が出たらその時に直す)

Apply・直接編集・取り込みは、渡した部分YAML(モデル定義YAMLの形で、変えたい部分だけ)を下書きの今の中身に重ねる。
実装は`core/infra/io/model_definition_patch.py`。

| # | 場面 | 規則 |
| --- | --- | --- |
| 1 | 重ねる先 | 下書きの今の中身(id・key付きの写し)。参照{ref: key}は重ねた後のkeyで解決する(最新の中身のkeyを使う) |
| 2 | 一覧の要素の特定 | idがあればidで、無ければkeyで同じ要素を探して重ねる。無ければ末尾に追加 |
| 3 | 値の上書き | 同じ場所の値は部分YAMLの値で上書きする(分割ファイルの読み込みは今までどおり食い違いをエラーにする) |
| 4 | 値を消す | `null`を書くと、その属性を消す |
| 5 | idもkeyも無い一覧 | 書いた一覧で丸ごと置き換える: 作品の`characters`・`relationships`(参照)・企画書の`characters`・エージェントの`rules`・`prohibitions`・`tasks`(nullで消すと職能の既定に戻る)・`members`・`involved_relationships`・`characteristics`・`features`・`endings`・`examples` |
| 6 | 要素の削除 | `{id: …, delete: true}`(keyでも可)。所有している子も消える。消した要素を参照している所が残れば、反映しない(参照切れのValueError) |
| 7 | `dramaturgy:`(単数) | `dramaturgies`の1要素として扱う(規則2で特定) |
| 8 | 置き換え | 取り込みは`replace`を選べば、下書きの中身を全体で置き換える(複数の文書は分割ファイルと同じ規則で重ね合わせる) |

- 1回の操作で渡した複数の文書(`---`区切り・複数のファイル)は、分割ファイルと同じ規則で1つにまとめてから重ねる
  (分割した文書は属する作品を書かないため。まとめるときnullは無視されるので、値を消すには1つの文書で渡す)。
- 重ねた結果は組み立て直して検証してから履歴に積む(形の誤り・参照切れなら積まない)。
- 確定は1つのトランザクション(正本の書き直し・版の追加・下書きをconfirmed)。途中で失敗すれば正本も版も変わらない。

## 置き場所(案)

- 今の`project.db`(1プロジェクト=1DB)に置く。そのため各テーブルに`project_id`を持たせない。
- 各テーブルの`id`は、モデルの識別子(UUIDの文字列)。
- 並び順の列は`sort_order`にする(SQLの予約語`order`を避ける)。値はモデルの`order`。
- 列挙型(`VoiceGender`・`StringDateType`・`TemporalRelationKind`・`SentenceEndingKind`)は値の文字列で持つ。

## A. 版と下書き

```sql
-- ③ 版: 確定した時点の作品モデル全体の写し
model_version (
  version      INTEGER PRIMARY KEY,   -- 1からの連番
  created_at   TEXT NOT NULL,
  draft_id     TEXT,                  -- どの下書きを確定した版か
  note         TEXT,                  -- 版の説明(任意)
  snapshot     TEXT NOT NULL          -- モデル定義YAML(プロジェクト全体)
)

-- 下書き: 確定した版を元に作り、確定すると①に反映する
draft (
  id            TEXT PRIMARY KEY,
  title         TEXT,
  base_version  INTEGER,              -- 元にした版(空=何もない状態から)
  status        TEXT NOT NULL,        -- open / confirmed / discarded
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
)

-- ② 下書きの履歴: Apply・直接編集・Undoのたびに1行ずつ積む
draft_revision (
  draft_id     TEXT NOT NULL REFERENCES draft(id),
  revision     INTEGER NOT NULL,      -- 0=作成時
  operation    TEXT NOT NULL,         -- create / apply / edit / undo / import
  created_at   TEXT NOT NULL,
  snapshot     TEXT NOT NULL,         -- モデル定義YAML(プロジェクト全体)
  PRIMARY KEY (draft_id, revision)
)
```

QIDMのdraftsにあった根拠(evidence)・会話(conversation)は、対話方式の制作(保留)を設計するときに足す。

## B. ① 正本(作品のテーブル)

⊂は持ち主(コンポジション)。持ち主を消すと一緒に消える。

| テーブル | 列 |
| --- | --- |
| `temporal_node` | id・label・date_type・string_date |
| `location` | id・name・latitude・longitude・address・instruction・description |
| `character` | id・name・reading・gender・age・speech_first_person・speech_tone・speech_description |
| `sentence_ending` ⊂character | character_id・sort_order・kind・examples(JSONの配列)・description |
| `characteristic` ⊂character | character_id・sort_order・item・definition・description |
| `additional_feature` ⊂characteristic | character_id・characteristic_order・sort_order・item・value・definition・description |
| `biography` ⊂character | id・character_id・sort_order・period_id→temporal_node・episode |
| `character_group` | id・name・kind・description |
| `relationship` | id・source_id・target_id→character・label・period_id・description・form_of_address・tone |
| `dramaturgy` | id・sort_order・title・synopsis・input_language・output_language・premise_text |
| `proposal` ⊂dramaturgy | dramaturgy_id(作品ごとに1行)・title・catchphrase・logline・intent・target_area・synopsis |
| `proposal_character` ⊂proposal | dramaturgy_id・sort_order・name・description |
| `agent` ⊂dramaturgy | id・dramaturgy_id・sort_order・kind(職能。YAMLの区画名の単数形)・name・role・persona・rules・prohibitions(JSONの文字列の一覧)・casting_id(Actorだけ。ID参照で制約なし)・voice_name |
| `agent_task` ⊂agent | agent_id・sort_order・code・title・description・rules・prohibitions(JSON) |
| `temporal_edge` ⊂dramaturgy | id・dramaturgy_id・sort_order・label・kind・source_id・target_id→temporal_node |
| `cast` ⊂dramaturgy | id・dramaturgy_id・sort_order・character_id・performance_title・performance_description・performance_pace・voice_gender・language・accent |
| `act` ⊂dramaturgy | id・dramaturgy_id・sort_order・title・synopsis |
| `scene` ⊂act | id・act_id・sort_order・title・synopsis・period_id・location_id・situation_location_id・situation_description・situation_time_of_day・situation_environment |
| `line` ⊂scene | id・scene_id・sort_order・cast_id→cast・text |
| `script_element` ⊂scene | id・scene_id・sort_order・kind(dialogue / sound_effect / atmosphere / music)・Dialogueの列(line_id・cast_id・text・action・direction_style・direction_pace・direction_dynamics・direction_emotion・direction_pause_after・translated_text・has_situation・situation_location_id・situation_description・situation_time_of_day・situation_environment) |

多対多(中間テーブル。並びを持つものは`sort_order`付き):
`dramaturgy_character`・`dramaturgy_relationship`・`character_group_member`・`biography_relationship`。

### 値オブジェクト・継承の扱い

- 1つだけ持つ値(Premise・Situation・Direction・Performance・SpeechStyleの単純な属性)は、持ち主のテーブルの列にする。
- 一覧で持つ値(Characteristic→AdditionalFeature・SentenceEnding)は子テーブルにする。識別子が無いので、持ち主のidと並び順で特定する。
- `ScriptElement`の継承は1テーブル+種別の列(`kind`)。Dialogue以外の3つは今は空のため。
- `Character.relationships`は保存しない(読むときに`relationship`から組み立てる)。
- `Script`はクラスとしては残すが、DBでは`line`がsceneに直接ぶら下がる。
- `Dialogue.line_id`・`cast_id`はモデルでID参照なので、外部キーの制約を付けない。
- `Dialogue.situation`は省略できるので、`has_situation`で「省略」と「空の状況」を区別する。

## 公開API・HTTP(2026-10-01)

方針は [architecture.md](architecture.md) 7節「作品モデルの公開API」。作品の中身はモデル定義YAMLの形(`DramaturgyDefinition`。
値を指定した属性だけを書く)で返し、Apply・直接編集・取り込みは本文の部分YAMLをそのまま受け取る。

| メソッドとパス(`/projects/{project_id}`の下) | 処理(`core/service/api`) | 結果 |
| --- | --- | --- |
| GET `/drama-model` | `drama_model.get_model` | 正本 |
| GET `/drama-model/versions` | `drama_model.list_versions` | 今の版と版の一覧 |
| GET `/drama-model/versions/{version}` | `drama_model.get_version` | 版の写し |
| POST `/drama-drafts`(`title`) | `drama_draft.create_draft` | 下書き(最新の版から) |
| GET `/drama-drafts`(`?status=`) | `drama_draft.list_drafts` | 下書きの一覧 |
| GET `/drama-drafts/{draft_id}` | `drama_draft.get_draft` | 下書きの管理情報 |
| GET `/drama-drafts/{draft_id}/content`(`?revision=`) | `drama_draft.get_draft_content` | 下書きの中身 |
| GET `/drama-drafts/{draft_id}/revisions` | `drama_draft.list_revisions` | 履歴 |
| POST `/drama-drafts/{draft_id}/apply`(本文=部分YAML) | `drama_draft.apply_proposal` | 履歴の番号 |
| POST `/drama-drafts/{draft_id}/edit`(本文=部分YAML) | `drama_draft.edit_draft` | 履歴の番号 |
| POST `/drama-drafts/{draft_id}/import`(本文=YAML、`?replace=`) | `drama_draft.import_yaml` | 履歴の番号 |
| POST `/drama-drafts/{draft_id}/import-path`(`path`・`replace`) | `drama_draft.import_path` | 履歴の番号 |
| POST `/drama-drafts/{draft_id}/undo` | `drama_draft.undo` | 履歴の番号 |
| POST `/drama-drafts/{draft_id}/confirm`(`note`) | `drama_draft.confirm_draft` | 版の番号 |
| POST `/drama-drafts/{draft_id}/discard` | `drama_draft.discard_draft` | 下書きの管理情報 |

エラー: プロジェクト・下書き・版・取り込むパスが無ければ404、元にした版が古い確定は409、YAMLの形・参照の誤り・openでない下書きの
変更・取り消せる変更が無いUndoは400。テストは`tests/api/test_drama_draft.py`。

- エージェントのタスクは`code`でシステム既定(`core/default/agents/`)と結び付ける。システム既定のタスクの`code`を変える・消すと、
  それを持つ版・下書きはモデル定義YAMLとして読み直すときにエラーになる(システム既定に無いcode)。変えるときは移し替えを考える。
