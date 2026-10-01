# モデルの設計(`core/model/`)

2026-09-30時点の組み立て。決定の経緯は [future_design.md](future_design.md)「モデルは作品とエージェントの2本立て」。
2026-09-30に**クラスと属性だけ**を実装した。**構成はユーザーの承認前(レビュー中)**。機能(メソッド・Factory)は構成の承認後。**(暫定)** と書いた箇所は、細部を決めずに最も単純な形で置いたもの。基本の部分を動かしてから見直す。

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
Project(core/project)
 └ Dramaturgy ×n ─ 作品全体。メタメタストーリー、input_language / output_language
     ├ Premise ─ 前提の知識
     ├ Character ×n ─ 登場しない人物も含む。人物像の特徴(Characteristic ×n → AdditionalFeature ×n)を持つ
     │   └ Biography ×n ─ 経歴(period: TemporalNode、episode、involved_relationship: Relationship)
     ├ Cast ×n ─ character: Character に声を割り当てた配役。台詞の話者
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

所有者を持たない: TemporalNode(TemporalEdgeの両端)、Location、Relationship(source/target: Character、period: TemporalNode)
```

`core/model/`には純粋なモデルだけを置く(2026-09-30ユーザー決定)。API・生成AI・ファイル・DBに関わるもの(ファイルのパス、
Datasetのfile_id、生成AIへの指示、生成器等)を持たせない。資料とDramaturgyの結び付けは、QIDMのDatasetとDomainと同じく
store(台帳)の側で持つ。

## `core/model/drama/`

| ファイル | クラス | 属性 |
| --- | --- | --- |
| `dramaturgy.py` | `Dramaturgy` | `id`・`title`・`synopsis`(メタメタストーリー)・`input_language`・`output_language`・`premise`・`characters`・`casts`・`acts`・`history` |
| `premise.py` | `Premise` | `text` |
| `act.py` | `Act` | `id`・`order`・`title`・`synopsis`(メタストーリー)・`scenes` |
| `scene.py` | `Scene` | `id`・`order`・`title`・`synopsis`・`period: TemporalNode`・`location: Location`・`script`・`elements` |
| `script.py` | `Script` | `lines` |
| | `Line` | `id`・`order`・`cast: Cast`・`text` |
| `script_element.py` | `ScriptElement`(基底) | `id`・`order` |
| | `Dialogue` | `line_id`・`cast_id`(ID参照)・`text`・`action`(ト書き)・`direction`・`translated_text`(output_languageへの訳文) |
| | `Direction` | `style`・`pace`・`dynamics`・`emotion`・`pause_after`(言葉で表す間。ミリ秒にしない) |
| | `SoundEffect`・`Atmosphere`・`Music` | 空 |
| `cast.py` | `Cast` | `id`・`character: Character`・`provider`・`voice_name`・`language`・`accent`・`notes` |
| `character.py` | `Character` | `id`・`name`・`reading`・`gender`・`age`・`speech_style`・`characteristics: list[Characteristic]`・`biographies`・`relationships`(関わる人物関係。sourceでもtargetでも。所有はしない) |
| `feature.py` | `Characteristic` | `item`・`definition`・`description`・`features: list[AdditionalFeature]`(特徴=項目のまとまり。2階層まで) |
| | `AdditionalFeature` | `item`(項目)・`value`(値)・`definition`(itemの意味。空でもよいが、架空の言葉等では定義を書く)・`description`(補足) |
| | `Biography` | `id`・`period: TemporalNode`・`episode`・`involved_relationship: Relationship` |
| `relationship.py` | `Relationship` | `id`・`source: Character`・`target: Character`・`label`・`period: TemporalNode`・`description`。作ると両端の人物の`relationships`に加わる(2026-09-30、人物から人物関係を引けるように) |
| `location.py` | `Location` | `id`・`name`・`latitude`・`longitude`・`address`・`instruction`・`description` |
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

エージェントは職能ごとのクラス(基底`Agent`のサブクラス)。どの手段で動かすか(利用者・文章生成・音声合成・プログラム)は
モデルに持たず、処理の側(`service/process`)が決める。エージェントどうしのやり取り(発注・提案と反映・利用者との相談)はエージェントのモデルではないので、
ここには置かない(公開API・処理の側で設計する。QIDMのdraftsに相当)。

| ファイル | クラス | 実行の手段 | 固有の属性 | 読む | 書く |
| --- | --- | --- | --- | --- | --- |
| `agent.py` | `Agent`(基底) | — | `id`・`name`・`persona`(性格づけ) | | |
| `producer.py` | `Producer` | human(利用者) | なし | すべて | Premise・提案の反映/却下 |
| `researcher.py` | `Researcher` | text+検索 | なし | 資料・Premise | (根拠のみ。作品は書き換えない) |
| `casting_director.py` | `CastingDirector` | text | `provider`(声を選ぶ音声合成の提供元) | Character | Cast |
| `scriptwriter.py` | `Scriptwriter` | text | なし | Premise・Character・Relationship・TemporalNode・あらすじ | Character・Biography・Relationship・あらすじ・Script |
| `director.py` | `Director` | text | なし | Script・Character・Location | ScriptElement |
| `stage_manager.py` | `StageManager` | program | なし | ScriptElement・音声 | キューシート・翻訳の呼び出し(**暫定**) |
| `actor.py` | `Actor` | speech | `casting_id`(Castごとに1つ。ID参照) | Dialogue・Cast | 台詞の音声 |
| `sound_engineer.py` | `SoundEngineer` | program | なし | キューシート | シーンの音声 |

「読む」「書く」は、機能を定義するときにコードへ入れる。

## モデルの組み立てと生成AIとの受け渡し(2026-09-30ユーザー決定。作品の側は実装済み、agentのFactoryは未実装)

QIDMに準じる(`core/model/factory.py`・`core/schema/formats/domain_definition.py`・`core/infra/io/model_definition_*`)。

- **Factoryは関数の集まり**(クラスの継承にしない): `core/model/drama/factory.py`・`core/model/agent/factory.py`に`build_*`を並べる。
  値からエンティティを組み立てて返すだけで、DB・ファイルに触れない。既存の識別子を保てる(QIDMの`_keeps_id`)。
  YAMLからの取り込みと、生成AIの提案の反映が、同じ組み立ての規則を共有する。
- 生成AIにはモデルのオブジェクトを直接渡さず、**モデル定義YAML**(`core/schema/formats/`)の文字列として渡す。返させる型は
  `core/prompt/`。モデル定義YAMLは、準備の5項目の「YAMLのモデル定義ファイルからの取り込み」と同じ形を兼ねる。
- モデルとYAMLの変換は`core/infra/io/`(読むときにFactoryを使う)。
- モデル定義YAMLは、**1つのファイルでも、分割した複数のファイルでも読み書きできる**(2026-09-30ユーザー)。

### モデル定義YAMLの形(2026-09-30実装。**形はユーザーのレビュー前**)

| 役割 | 場所 |
| --- | --- |
| 形(pydantic) | `core/schema/formats/dramaturgy_definition.py`(`DramaturgyDefinition`。区画・参照の規則はdocstring) |
| 組み立て | `core/model/drama/factory.py`(`build_*`。識別子を持つエンティティは`id=`で既存の識別子を保つ) |
| 読む | `core/infra/io/model_definition_reader.py`(`read_dramaturgy(ファイルかディレクトリ)`・`build_dramaturgy_from_yaml(*文字列)`) |
| 書く | `core/infra/io/model_definition_writer.py`(`write_dramaturgy`=1ファイル、`write_split_dramaturgy`=区画ごとのファイル) |

- 1つのYAMLが1つのDramaturgy。**コンポジション(所有)はYAMLでも入れ子にする**(2026-09-30ユーザー): `dramaturgy`の中に
  `premise`・`characters`(`characteristics`→`features`・`biographies`)・`casts`・`acts`(`scenes`→`script.lines`・`elements`→`direction`)・`history.edges`。
  所有者を持たない要素(`temporal_nodes`・`locations`・`relationships`)は、`dramaturgy`と並ぶ最上位に書いて参照する。
- 分割: 分けた文書も同じ入れ子の形で、その一部だけを持つ(例: `dramaturgy: {casts: [...]}`)。読むときはすべての文書(ファイル・`---`区切り)を
  重ね合わせる(対応表は同じキーどうしを重ね、一覧は`id`か`key`が同じ要素どうしを重ね、それ以外は読んだ順につなげ、同じ場所の異なる値はエラー)。
  これにより、**シーンと台詞(Script)も別のファイルに書ける**(2026-09-30ユーザー): 属する幕・シーンを`id`か`key`で示す
  (`dramaturgy: {acts: [{key: 幕, scenes: [{key: シーン, script: {...}}]}]}`)。そのため幕とシーンも`key`を持てる(参照には使わない)。
  ディレクトリを読むときは配下の`*.yaml`・`*.yml`をすべて(名前順)。
- 書くときの分け方: `SPLIT_FILES`(`dramaturgy`・`temporal`・`locations`・`characters`・`casts`・`acts`の6ファイル。`acts`は幕の属性だけ)と、
  シーンを制作の段階で分けたシーンごとのファイル(旧来の`plot/`・`script/`・`scene/`に対応): `plots/act_NNN_scene_NNN.yaml`(プロット=
  シーンの題・あらすじ・時期・場所)・`scripts/…`(台詞)・`scenes/…`(演出付きの原稿)。**プロット単位で取り込める**(2026-09-30ユーザー。
  Plotのクラスは作らず、プロット=`Scene.synopsis`)。書き直すとき、減ったシーンの古いファイルは消し、それ以外の名前のYAMLがあれば書かない。

### サンプルデータ(`apps/sample_data/`)と、変換で見つかった構造上の問題(レビュー用)

`apps/sample_project/`の`character/*.txt`・`plot/*.txt`を、分割方式のモデル定義YAMLに変換したもの(2026-09-30)。原文は言い換えずに写し、
人物像は原文の見出しを特徴(`Characteristic`)に、「**項目**: 値」を項目(`AdditionalFeature`)にした。見出し「過去のエピソード」「人物関係」も特徴にし、その前書きを`description`に、名前の無い人物を「人物関係」の項目にした。人物は1人1ファイル(`characters/`)。
行ごとの照合で、原文の情報はすべて読み込んだモデルにあることを確かめた(人物関係40件はすべて人物から引ける。コメントに残したものは無い)。プロット5件のあらすじは一字一句同じ。

モデルに無理に押し込まなかったもの(クラスの設計で決めること):

| # | 原文 | 問題 | 今の扱い |
| --- | --- | --- | --- |
| 1 | 名前の無い人物(吹奏楽部の顧問・彼氏1人目・2人目) | `Character.name`が必須なので人物にできず、「人物関係」の項目にした。原文でどの時期の見出し(中学校時代・大学時代)の下にあったかは、`AdditionalFeature`に時期が無いので残らない | 「人物関係」の項目 |
| 2 | 1つの経歴に複数の人物関係(「佐々木親子との出会い」等) | `Biography.involved_relationship`は1つだけ | 1人に関わると読めるものだけ結んだ |
| 3 | 人物関係の本文に、相手の人物像(職業・性格・年齢)が混ざっている | 相手の`Character.characteristics`と人物関係の説明を分けるには、原文を書き換える必要がある | 人物関係の`description`に原文のまま。年齢は冒頭にあるものだけ`age`にも写した |
| 4 | 見出し「家族」「現在の職場」 | 家族は時期ではない(`period`なし)。「現在の職場」は時期と場所が混ざっている | 家族は`period`なし、「喜一の現在の職場」は時期として置いた |
| 5 | 作品の題・幕 | 原文に題も幕の区切りも無い。`Dramaturgy.title`は必須、シーンは幕に属する | 題は人物のファイルにある物語の名前「明治の弥次喜多道中」、幕は1つ |
| 6 | 台詞の話者の呼び名(`script/*.txt`の「喜一：」、`actors.yaml`の`label`・`character_name`) | `Character`に呼び名(短い名前)が無い。制作の流れでは話者名をフルネームにし、生成AIが空白を詰めて書く(「加藤喜一：」)ので、照合で空白を無視している | `script/`は未変換。呼び名(`label`)は`casts.yaml`のコメント |
| 7 | `actor/actors.yaml`の`personality_title`・`personality_description`・`gender`・`label` | `Cast`に当たる属性が無い(`notes`は声の話し方)。音声合成への指示の「AUDIO PROFILE」から性格が抜ける | 配役(人物・声・accent)は`casts.yaml`に変換、ほかはコメント |
| 8 | 原稿(`scene/*.yaml`)の各台詞の`context`(場所・状況) | `Dialogue`に当たる属性が無い(`action`は動き・表情)。音声合成への指示の「THE SCENE」に使っている | 制作の流れでは原稿を旧来の形の作業ファイルに置き、`scenes/`には書き戻さない |

時期ごとの要約(「人生の絶頂期と肥大したプライド。…」等)は、その時期の経歴(`Biography`)の先頭に置いた。
時間の位相は、人物ごとの時期を順に`meets`で結び(原文の見出しの順から。年齢からの推定はしていない)、2人のネットワークは時点「喜一と弥千代の出会い（城崎温泉）」だけで合流させた(出会いが両方の「現在」の間にある=`during`)。
- 参照: 参照先の`key`(定義の中だけの名前。人・生成AIがidを決めずに書くため)か`id`。書き出しは常に`id`で書き、`key`は書かない。
  `Dialogue.line_id`・`cast_id`はYAMLでは`line`・`cast`(同じくkeyかid)。
- `order`は省略すれば並びの中の位置(0から)。未知の属性はエラー(書き誤りを黙って捨てない)。

## 今の制作の流れとの対応

| 今 | このモデル |
| --- | --- |
| `character/*.txt` | `Character`(見出しを`characteristics`、時期ごとのエピソードを`biographies`、人物関係を`relationships`。`apps/sample_data`で変換済み) |
| `actor/actors.yaml` | `Cast` |
| `plot/*.txt` | `Scene.synopsis` |
| `script/*.txt` | `Script` |
| `scene/*.yaml` | `Scene.elements`(`Dialogue`) |
| `sound/*.mp3` | 結合した音声(キューシートはUMLに無い。未定) |
