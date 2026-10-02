# モデルの設計(`core/model/`)

2026-09-30時点の組み立て。決定の経緯は [future_design.md](future_design.md)「モデルは作品とエージェントの2本立て」。
2026-09-30に**クラスと属性だけ**を実装した。**構成は2026-10-01にユーザーが承認した**。機能(メソッド)はまだ無い。**(暫定)** と書いた箇所は、細部を決めずに最も単純な形で置いたもの。基本の部分を動かしてから見直す。

## 全体

- `core/model/drama/`=作られる作品、`core/model/agent/`=作品作りに参加する者。
- 集約の根はProject(`core/project/`。Drama=Project)。Projectは複数のDramaturgyを持つ(**暫定**。QIDMのDomainと同じ)。
- 各エンティティは`__init__`で識別子`id`(`core/model/identifier.py`のUUID)を振る(QIDMと同じ。既存の識別子を保つのはFactory)。
  **素のクラスで書く**([architecture.md](architecture.md) 4節)。名前・題は変更できる表示用の値。識別子はシステムが付け、
  生成AIに決めさせない([architecture.md](architecture.md) 6節)。
- **参照は、論理的に関連であるべきものは関連(オブジェクトへの参照)、ID参照でよいものは識別子で持つ**(2026-09-30ユーザー)。
  ID参照は`Dialogue.line_id`・`Dialogue.cast_id`(ユーザー指定)と`Actor.casting_id`(UMLで型がuuid)。それ以外はUMLの関連どおり。
- 論理的なモデルなので、すべての要素が所有者(コンポジション)を持つ必要はない(`TemporalNode`・`Location`・`Relationship`等)。
  最終的な配置はアプリケーションが決める(2026-09-30ユーザー)。
- A群なので、`genai`・`infra`・`service`・`schema`をimportしない。

構成の正本はユーザーのUMLクラス図(`AiDramaCreator`、`model`パッケージの`agent`・`drama`。2026-09-30)。

```
Project(core/project。今はモデル定義の読み込み結果 ModelDefinition に仮置き)
 ├ Character ×n ─ 登場しない人物も含む。作品をまたいで共有できる。人物像の特徴(Characteristic ×n → AdditionalFeature ×n)を持つ
 │   └ Biography ×n ─ 経歴(period: TemporalNode、episode、involved_relationships: Relationship ×n)
 ├ CharacterGroup ×n ─ 人物のまとまり(家族・職場等。members: Character ×n を参照。kindは自由に書く)
 ├ Relationship ×n ─ 人物関係(source/target: Character、period: TemporalNode、form_of_address)
 └ Dramaturgy ×n ─ 作品全体。メタメタストーリー、input_language / output_language
     ├ (参照) characters: Character ×n・relationships: Relationship ×n ─ この作品に関わる人物・人物関係(所有しない)
     ├ Premise ─ 前提の知識
     ├ Proposal ─ 企画書(初期シード。題・あらすじ・登場人物は作品と共有しない)
     │   └ ProposalCharacter ×n ─ 企画書の登場人物(仮の設定。名前と説明だけ。Characterとは別)
     ├ Cast ×n ─ character: Character の配役(演じ方・声の性別)。台詞の話者
     ├ BaseAgent ×n ─ 作品作りに参加するエージェント(作品ごとに文面を書き換えられる。下の「core/model/agent/」)
     ├ History ─ TemporalEdge ×n(時間の位相)
     └ Act ×n ─ メタストーリー
         └ Scene ×n ─ あらすじ、period: TemporalNode(描く時期)、location: Location
             ├ Script ─ 台詞の段階(Scriptwriter)
             │   └ Line ×n ─ cast: Cast
             └ ScriptElement ×n ─ 演出付きの原稿の段階(Director)
                 ├ Dialogue(line_id・cast_id・ト書き・Direction・訳文)
                 ├ SoundEffect(空)
                 ├ Atmosphere(空)
                 └ Music(空)

所有者を持たない: TemporalNode(TemporalEdgeの両端)、Location、SiteFlow(Locationの間の移動)
人物・人物関係の持ち主はProject(2026-10-01ユーザー決定。作品は参照で持つ。Projectの作り直しまでは ModelDefinition に仮置き)
場所・移動の持ち主もProjectで、作品は使うものを参照で持つ(2026-10-02ユーザー決定。シリーズの別の作品の場所まで並ばないよう、作品ごとに取り込む)
```

`core/model/`には純粋なモデルだけを置く(2026-09-30ユーザー決定)。API・生成AI・ファイル・DBに関わるもの(ファイルのパス、
Datasetのfile_id、生成AIへの指示、生成器等)を持たせない。資料とDramaturgyの結び付けは、QIDMのDatasetとDomainと同じく
store(台帳)の側で持つ。

## `core/model/drama/`

| ファイル | クラス | 属性 |
| --- | --- | --- |
| `dramaturgy.py` | `Dramaturgy` | `id`・`title`・`synopsis`(メタメタストーリー)・`input_language`・`output_language`・`premise`・`proposal`(企画書)・`characters`(参照)・`relationships`(参照)・`locations`(参照)・`site_flows`(参照)・`casts`・`acts`・`history`。人物・人物関係・場所・移動は所有しない(2026-10-01、場所・移動は2026-10-02) |
| `premise.py` | `Premise` | `text` |
| `proposal.py` | `Proposal` | `title`・`catchphrase`(キャッチコピー)・`logline`(ログライン)・`intent`(企画意図)・`target_area`(対象地域。文字列、暫定)・`synopsis`(企画書のあらすじ)・`characters`。作品制作の初期シードで、仮の設定が多いため、題・あらすじ・登場人物を作品と共有しない。`Dramaturgy.synopsis`は作品を確定する段階で(生成AIの力を借りて)作るもので別。後から修正できる(すべて省略可)(2026-10-01ユーザー決定。UMLへの反映はユーザー) |
| | `ProposalCharacter` | `name`・`description`(企画書の登場人物。仮の設定で、`Character`とは別) |
| `act.py` | `Act` | `id`・`order`・`title`・`synopsis`(メタストーリー)・`scenes` |
| `scene.py` | `Scene` | `id`・`order`・`title`・`synopsis`・`period: TemporalNode`・`location: Location`・`situation: Situation`(場面の状況。場所はlocationが持つ)・`script`・`elements` |
| `situation.py` | `Situation` | `location: Location`(参照)・`description`(状況)・`time_of_day`(時間帯)・`environment`(天候・環境)。シーン・台詞が値として所有する(2026-10-01) |
| `script.py` | `Script` | `lines` |
| | `Line` | `id`・`order`・`cast: Cast`・`text` |
| `script_element.py` | `ScriptElement`(基底) | `id`・`order` |
| | `Dialogue` | `line_id`・`cast_id`(ID参照)・`text`・`action`(ト書き)・`direction`・`translated_text`(output_languageへの訳文)・`situation`(場面の途中で状況が変わるときだけ。無ければシーンの状況) |
| | `Direction` | `style`・`pace`・`dynamics`・`emotion`・`pause_after`(言葉で表す間。ミリ秒にしない) |
| | `SoundEffect`・`Atmosphere`・`Music` | 空 |
| `cast.py` | `Cast`・`CastBilling` | `id`・`character: Character`(演じる人物。関連)・`performance: Performance`(演じ方)・`voice_gender: VoiceGender`(声を当てるときの性別)・`language`・`accent`・`billing: CastBilling`(役の重さ。lead=主役・supporting=脇役・minor=端役。未設定可。2026-10-02)。声は演者(`Actor`)が持つ(2026-10-01) |
| | `Performance` | `title`(見出し。例: Strict Guy)・`description`・`pace`(話す速さ。2026-10-01) |
| | `VoiceGender` | male・female・neutral(中性的)。人物の性別(`Character.gender`。不明・両性もあり得る)とは別に、配役で決める(2026-10-01ユーザー) |
| `character.py` | `Character` | `id`・`name`・`reading`・`gender`・`age`・`speech_style: SpeechStyle`(話し方)・`characteristics: list[Characteristic]`・`biographies`・`relationships`(関わる人物関係。sourceでもtargetでも。所有はしない) |
| `speech_style.py` | `SpeechStyle` | `first_person`(一人称)・`tone`(相手を問わない既定の口調)・`endings: list[SentenceEnding]`・`description`(2026-10-01) |
| | `SentenceEnding` | `kind: SentenceEndingKind`・`examples`(例の一覧)・`description` |
| | `SentenceEndingKind` | normal(通常)・conjecture(推測)・question(疑問)・negation(否定)・command(命令)・request(依頼)・exclamation(感嘆) |
| `feature.py` | `Characteristic` | `item`・`definition`・`description`・`features: list[AdditionalFeature]`(特徴=項目のまとまり。2階層まで) |
| | `AdditionalFeature` | `item`(項目)・`value`(実際に使う値)・`definition`(itemの意味。空でもよいが、架空の言葉等では定義を書く)・`description`(説明文やメモ) |
| | `Biography` | `id`・`period: TemporalNode`・`episode`・`involved_relationships: list[Relationship]`(関わる人物関係。複数でもよい。2026-10-01) |
| `character_group.py` | `CharacterGroup` | `id`・`name`・`kind`(自由に書く。例: 家族・職場)・`members: list[Character]`(参照)・`description`。持ち主はProject(2026-10-01) |
| `relationship.py` | `Relationship` | `id`・`source: Character`・`target: Character`・`label`・`period: TemporalNode`・`description`・`form_of_address`(sourceがtargetをどう呼ぶか。場面による使い分けは扱わない)・`tone`(sourceがtargetに対して話す口調)(2026-10-01)。作ると両端の人物の`relationships`に加わる(2026-09-30、人物から人物関係を引けるように) |
| `location.py` | `Location` | `id`・`name`・`geometry`(形。WKTの文字列、WGS84で経度・緯度の順。2026-10-02に`latitude`・`longitude`から替えた)・`address`・`instruction`(その場所で案内すること)・`description`(その場所の事実)。位置連動の音声(Locatone等)では、シーンの場所は面で、再生エリアに当たる |
| `site_flow.py` | `SiteFlow`・`SiteFlowDirection` | `id`・`name`・`geometry`(道筋の線。WKTのLINESTRING)・`direction`(forward・backward・both。線を引いた向き(origin→destination)に対する移動の向き。未設定可)・`origin: Location`・`destination: Location`(参照。線の始点・終点を含む場所)。2026-10-02ユーザー決定 |
| `temporal.py` | `TemporalNode` | `id`・`label`(言葉としての時期)・`date_type: StringDateType`・`string_date` |
| | `TemporalEdge` | `id`・`label`・`kind: TemporalRelationKind`・`source: TemporalNode`・`target: TemporalNode` |
| | `TemporalRelationKind` | before・meets・overlaps・during・starts・finishes・equals(Allenの区間代数) |
| | `StringDateType` | datetime・date・year・month・day・time・hour・minutes・seconds・string_expression |
| `history.py` | `History` | `edges`(TemporalEdge) |

規則(機能の段階で守らせる): どのTemporalNodeも、ほかのTemporalNodeとの関係を少なくとも1つ持つ。
時間の位相は1つにつながっている必要はない(2026-09-30ユーザー): 互いを知らない人物は別々の時間のネットワークにあり、出会った時点で
初めて合流する。人物どうしの時期を、出会う前について無理に結ばない。
UMLからの直し(ユーザー指示): 型が`int`になっていた属性の修正漏れを直した(`Dramaturgy`の各属性・`CastingDirector.provider`・
`Dialogue.translated_text`)。綴りを直した(`langage`→`language`・`characterics`→`characteristics`・`MINITES`→`MINUTES`)。
UMLからの変更(2026-09-30ユーザー承認): `Profile`をなくし、`Character`が`characteristics: list[Characteristic]`を直接持つ
(`Profile`は`characteristics`しか持たない中継ぎだったため)。人物像の項目は決め打ちにせず、`Characteristic`(項目のまとまり)と
`AdditionalFeature`(項目)の2階層で書く(`feature.py`)。
クラス名`cast`はPythonの慣習で`Cast`。UMLで`Cast`から`Character`への関連の役割名は`cast`だが、属性名は`character`にした。

音声タグ(`AudioTag`)は`Dialogue.text`の中に書く。一覧は音声合成の提供元に依存するので`genai`側(**暫定**)。

## `core/model/agent/`

エージェントは**生成AIが担う職能**で、職能ごとのクラス(抽象クラス`BaseAgent`のサブクラス)。**作品(`Dramaturgy.agents`)が所有する**
(作品ごとに文面を書き換えられる。下書き・版・DBにも入る。2026-10-01ユーザー決定)。**Producerは利用者本人なので、モデルに置かない**
(2026-10-01ユーザー決定)。チャットで対話するかどうかに関わらず、生成AIを使う職能(文章生成・音声合成)はすべてエージェント。
どの生成AI(提供元・モデル)で動かすかはモデルに持たず、処理の側(`service/process`)が決める(仮に`project.yaml`の`genai`)。
演者(`Actor`)は、どの声で演じるか(`voice_name`)を自分で持つ(2026-10-01ユーザー決定)。2026-10-02からは音声合成の提供元(`tts_provider`)・モデル(`tts_model`)も1組持つ
(空ならproject.yamlの`genai.tts`)。`voice_name`は提供元の声の識別子(Geminiは声の一覧の`id`。例: `ja-jp-advisor-1`)。

**生成AIへのプロンプトを組み立てるための情報を属性として持つ**(プロンプトの文そのもの・応答の型・渡す情報の範囲は持たない。組み立ては
`core/prompt`、実行は`service/process`。2026-10-01ユーザー決定。ai_drama_creator_2のプロンプトの節(Role・Tasks・厳守事項・禁止事項)を参考にした):

| ファイル | クラス | 属性 |
| --- | --- | --- |
| `base_agent.py` | `BaseAgent`(抽象) | `id`・`name`・`role`(役割の説明)・`persona`(性格づけ)・`rules`(どのタスクでも守ること)・`prohibitions`(どのタスクでもしてはいけないこと)・`tasks: list[AgentTask]`。既定の文面は持たない(下の「既定」) |
| `agent_task.py` | `AgentTask` | `code`(タスクの識別子。職能ごとにシステム既定で決まる)・`title`・`description`・`rules`・`prohibitions`。**職務の定義**で、発注(担当・状態・結果)ではない |

- エージェントは作品ごとに書き換えた後の**全文**を持つ。
- **既定は2段**(2026-10-02ユーザー決定):
  - **システム既定**(正本): `core/default/agents/<職能>.yaml`(Actorを含む7職能。作品の分割ファイルと同じ形`dramaturgy.agents`)。
    読み込みは`core/infra/io/agent_default_reader.py`。モデル定義YAMLで省略した項目(role・rules・prohibitions、タスクと
    タスクの中の項目)はシステム既定で補う(`complete_agent_spec`)。モデル(`core/model`)はファイルを読まないので、既定の文面を持たない。
  - **ユーザー既定**: `<プロジェクト>/user_default/agents/<職能>.yaml`(Actor以外の6職能。プロジェクトごと)。プロジェクトの作成時に
    システム既定を複製し、無い職能は使うときに複製する(`core/infra/store/agent_default_store.py`)。新しい作品(New Dramaturgy)は
    必ずユーザー既定のエージェントを持ち、Agentsタブを開いたとき足りない職能はユーザー既定から読み込む。
- **タスクの一覧は職能ごとに固定**(システム既定のcodeで特定)。書き換えられるのは文面だけ。システム既定に無いcodeはエラー。
  タスクごとの応答の型・渡す情報・反映の処理は、codeで`core/prompt`・`service/process`の側と結び付ける。
- `AgentTask.code`は、モデル定義YAMLの`key`(書き出すたびに振り直す呼び名)と区別するため`key`にしなかった。
- システム既定の文面(役割・厳守事項・禁止事項・タスク)は**暫定**(2026-10-01。ユーザーの見直しを待つ)。
- **Actor(演者)は配役ごとに置く**ので、ユーザー既定とAgentsタブには出さない。声の設定はDramaturgy EditorのCastsタブで行う(2026-10-02)。

| ファイル | クラス | 生成AI | 固有の属性 | タスク(code。システム既定) |
| --- | --- | --- | --- | --- |
| `researcher.py` | `Researcher` | text+検索 | なし | `answer_question`・`check_consistency` |
| `casting_director.py` | `CastingDirector` | text | なし | `cast_character`・`assign_voice` |
| `scriptwriter.py` | `Scriptwriter` | text | なし | `draft_proposal`・`create_character`・`create_character_group`・`create_relationship`(Build with AI、2026-10-02)・`import_proposal_character`・`check_character_conflict`(2026-10-02)・`write_synopsis`・`write_dialogue` |
| `director.py` | `Director` | text | なし | `direct_scene` |
| `stage_manager.py` | `StageManager` | text(翻訳) | なし | `translate`(キューシートの組み立てはプログラムで、タスクにしない) |
| `sound_engineer.py` | `SoundEngineer` | (将来) | なし | `design_sound`(結合はプログラム) |
| `actor.py` | `Actor` | speech | `casting_id`(Castごとに1つ。ID参照)・`voice_name`(使う声)・`tts_provider`・`tts_model`(音声合成の提供元・モデル) | `perform_dialogue` |

エージェントどうしのやり取り(発注・提案と反映・利用者との相談)はエージェントのモデルではないので、ここには置かない
(公開API・処理の側で設計する。QIDMのdraftsに相当)。

## モデルの組み立てと生成AIとの受け渡し(2026-09-30ユーザー決定。作品・agentとも実装済み)

QIDMに準じる(`core/model/factory.py`・`core/schema/formats/domain_definition.py`・`core/infra/io/model_definition_*`)。

- **Factoryは関数の集まり**(クラスの継承にしない): `core/model/drama/factory.py`・`core/model/agent/factory.py`に`build_*`を並べる。
  値からエンティティを組み立てて返すだけで、DB・ファイルに触れない。既存の識別子を保てる(QIDMの`_keeps_id`)。
  YAMLからの取り込みと、生成AIの提案の反映が、同じ組み立ての規則を共有する。
- 生成AIにはモデルのオブジェクトを直接渡さず、**モデル定義YAML**(`core/schema/formats/`)の文字列として渡す。返させる型は
  `core/prompt/`。モデル定義YAMLは、準備の5項目の「YAMLのモデル定義ファイルからの取り込み」と同じ形を兼ねる。
- モデルとYAMLの変換は`core/infra/io/`(読むときにFactoryを使う)。
- モデル定義YAMLは、**1つのファイルでも、分割した複数のファイルでも読み書きできる**(2026-09-30ユーザー)。

### モデル定義YAMLの形(2026-09-30実装。2026-10-01ユーザー承認)

| 役割 | 場所 |
| --- | --- |
| 形(pydantic) | `core/schema/formats/dramaturgy_definition.py`(`DramaturgyDefinition`。区画・参照の規則はdocstring) |
| 組み立て | `core/model/drama/factory.py`(`build_*`。識別子を持つエンティティは`id=`で既存の識別子を保つ) |
| 読む | `core/infra/io/model_definition_reader.py`(`read_dramaturgy(ファイルかディレクトリ)`・`build_dramaturgy_from_yaml(*文字列)`) |
| 書く | `core/infra/io/model_definition_writer.py`(`write_dramaturgy`=1ファイル、`write_split_dramaturgy`=区画ごとのファイル) |

- 人物・人物のまとまり・人物関係は`dramaturgy`の外の最上位`characters:`・`character_groups:`・`relationships:`に書き、作品は`dramaturgy.characters`・`relationships`で`{ref: …}`の一覧として参照する(2026-10-01)。
- 作品が複数のとき(プロジェクトの作品モデル全体。DBの版・下書きの写し)は、最上位の`dramaturgies:`に一覧で書く(2026-10-01)。
  `dramaturgy:`と両方に書けば`dramaturgy`が先頭。読み込み結果`ModelDefinition`は`dramaturgies`(`dramaturgy`は作品が1つのときだけ)と、
  所有者の無い`temporal_nodes`・`locations`をすべて持つ。
- 1つのYAMLが1つのDramaturgy(`dramaturgy:`のとき)。**コンポジション(所有)はYAMLでも入れ子にする**(2026-09-30ユーザー): `dramaturgy`の中に
  `premise`・`characters`(`characteristics`→`features`・`biographies`)・`casts`・`acts`(`scenes`→`script.lines`・`elements`→`direction`)・`history.edges`。
  所有者を持たない要素(`temporal_nodes`・`locations`・`site_flows`・`relationships`)は、`dramaturgy`と並ぶ最上位に書いて参照する。
  形(`geometry`)はWKTで書き、読むときに検査して正規化する(`core/gis/geometry.py`。Z座標は捨てる)。移動の線の始点・終点が
  origin・destinationの面に入っていなければエラー(面でない場所と、形の無いものは確かめない)。
- 分割: 分けた文書も同じ入れ子の形で、その一部だけを持つ(例: `dramaturgy: {casts: [...]}`)。読むときはすべての文書(ファイル・`---`区切り)を
  重ね合わせる(対応表は同じキーどうしを重ね、一覧は`id`か`key`が同じ要素どうしを重ね、それ以外は読んだ順につなげ、同じ場所の異なる値はエラー)。
  これにより、**シーンと台詞(Script)も別のファイルに書ける**(2026-09-30ユーザー): 属する幕・シーンを`id`か`key`で示す
  (`dramaturgy: {acts: [{key: 幕, scenes: [{key: シーン, script: {...}}]}]}`)。そのため幕とシーンも`key`を持てる(参照には使わない)。
  ディレクトリを読むときは配下の`*.yaml`・`*.yml`をすべて(名前順)。
- 書くときの分け方: `SPLIT_FILES`(`dramaturgy`・`temporal`・`locations`・`characters`・`casts`・`acts`の6ファイル。`acts`は幕の属性だけ)と、
  シーンを制作の段階で分けたシーンごとのファイル(旧来の`plot/`・`script/`・`scene/`に対応): `plots/act_NNN_scene_NNN.yaml`(プロット=
  シーンの題・あらすじ・時期・場所)・`scripts/…`(台詞)・`scenes/…`(演出付きの原稿)。**プロット単位で取り込める**(2026-09-30ユーザー。
  Plotのクラスは作らず、プロット=`Scene.synopsis`)。書き直すとき、減ったシーンの古いファイルは消し、それ以外の名前のYAMLがあれば書かない。

### サンプルデータ(`apps/sample_data/令和但馬道中膝栗毛/`)と、変換で見つかった構造上の問題

旧来のサンプル(`apps/sample_project`。2026-10-01に削除)の`character/*.txt`・`plot/*.txt`・`actor/actors.yaml`を、分割方式のモデル定義YAMLに変換したもの(2026-09-30、10-01)。
作品は`drama/`、エージェントは`agent/`(2026-10-01ユーザーの構成)。原文は言い換えずに写し、
人物像は原文の見出しを特徴(`Characteristic`)に、「**項目**: 値」を項目(`AdditionalFeature`)にした。見出し「過去のエピソード」「人物関係」も特徴にし、その前書きを`description`に、名前の無い人物を「人物関係」の項目にした。人物は1人1ファイル(`characters/`)。
行ごとの照合で、原文の情報はすべて読み込んだモデルにあることを確かめた(人物関係40件はすべて人物から引ける。コメントに残したものは無い)。プロット5件のあらすじは一字一句同じ。

変換で見つかった構造上の問題(モデルに置き場所が無かったもの)は、2026-10-01にすべて決まった(呼び方・一人称・話し方と語尾・氏名不詳の人物・
複数の人物関係・人物関係の本文の書き換え・人物のまとまり・題・幕・話者名・場面の状況)。それぞれの扱いは以下。

時期ごとの要約(「人生の絶頂期と肥大したプライド。…」等)は、その時期の経歴(`Biography`)の先頭に置いた。
名前の無い人物(吹奏楽部の顧問・彼氏1人目・2人目)は、名前を「（氏名不詳）」にした人物にした(2026-10-01ユーザー)。見出しは人物関係の`label`、
「彼氏（1人目）：優しそうに見えて優柔不断なタイプ」の後半は、その人物の特徴「人物像」の`description`。
経歴の`involved_relationships`は、経歴の本文に人物関係の相手の名前(空白は無視)か「佐々木親子」が出てくるものを結んだ(同じ相手との関係が
複数あれば、経歴と同じ時期のもの)。呼び方は、話し方の文にある喜一→弥千代「キミ」・弥千代→喜一「キタさん」。一人称は原文に無いので、ユーザーの指定で喜一「オレ」・弥千代「あたし」(2026-10-01)。
人物のまとまり(`CharacterGroup`)は、原文の見出し「家族」「現在の職場」「喜一を不満に思うゼミ生3人組」と経歴の「佐々木親子」から5つ作った
(加藤家・水野家・都内大手IT企業・佐々木親子・ゼミ生3人組)。見出し「現在の職場」の人物関係の時期は「喜一の現在」にした(時点「喜一の現在の職場」はやめた)。
作品の題は、ユーザーの指定で「令和但馬道中膝栗毛〜ハチ北スキー場編〜」(2026-10-01)。幕は1つで、シーンは幕が1つでも必ず幕に入れる。
台詞の話者名は、キャラクター名(`Character.name`)を使う(旧来の短い呼び名「喜一：」には合わせない。2026-10-01ユーザー)。
話し方(「喋り方の特徴」)は、語尾を種類と例に分け、「通常の口調」の文を、既定の口調(`SpeechStyle.tone`)・相手に対する口調
(`Relationship.tone`。喜一→弥千代「タメ口」)・話す速さ(喜一の配役の`Performance.pace`「比較的ゆっくり」)・呼び方に分けた。
人物関係の本文に混ざっていた相手の人物像(職業・経歴・性格・先祖の話への考え・年齢)は、35件について相手の人物へ移した(2026-10-01、
ユーザーの依頼で書き換え)。移した先は相手の特徴「人物像」「先祖の話について」と`age`。人物関係の本文には関係の部分だけを残し、文が
つながらなくなる所だけ言葉を直した(例:「喜一とは対照的な明るく活発な性格ですが」→人物関係「喜一とは対照的な性格ですが」+人物像
「明るく活発な性格。」)。原文の句がすべて、書き換えた先のどこかにあることを照合で確かめた。
時間の位相は、人物ごとの時期を順に`meets`で結び(原文の見出しの順から。年齢からの推定はしていない。喜一の大学時代→現在は、間に就職があるので`before`)、2人のネットワークは時点「喜一と弥千代の出会い（城崎温泉）」だけで合流させた(出会いが両方の「現在」の間にある=`during`)。
- **識別子と参照は id / key / ref で統一する**(2026-10-01ユーザー決定):
  - `id`: エンティティの識別子(UUID)。システムが決める(人・生成AIに決めさせない)。書き出しでは必ず書き、読むときに無ければシステムが振る。
  - `key`: そのYAML一式の中だけで使う呼び名で、参照の受け口。モデルには残らない。書き出しでは種類と通し番号
    (`character_001`・`cast_001`・`scene_001_line_001`等)を振る。種類ごとに一意。
  - 参照: 常に`{ref: 参照先のkey}`(例: `character: {ref: character_001}`)。`id`では参照しない(参照先は同じYAML一式の中に
    なければならない。YAMLの外への参照は、必要になったときに足す)。`Dialogue.line_id`・`cast_id`はYAMLでは`line`・`cast`。
  - `apps/sample_data`の`id`は、`key`から決まるUUID(UUIDv5)で、変換し直しても変わらない。
- `order`は省略すれば並びの中の位置(0から)。未知の属性はエラー(書き誤りを黙って捨てない)。

## 今の制作の流れとの対応

| 今 | このモデル |
| --- | --- |
| `character/*.txt` | `Character`(見出しを`characteristics`、時期ごとのエピソードを`biographies`、人物関係を`relationships`。`apps/sample_data`で変換済み) |
| `actor/actors.yaml` | `Cast`(人物・演じ方・accent)と`Actor`(声)。`apps/sample_data`で変換済み |
| `plot/*.txt` | `Scene.synopsis` |
| `script/*.txt` | `Script` |
| `scene/*.yaml` | `Scene.elements`(`Dialogue`) |
| `sound/*.mp3` | 結合した音声(キューシートはUMLに無い。未定) |
