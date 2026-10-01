# 既知のバグ・技術的負債

## 不具合

- 現行の`Project`(`core/service/process/production/_legacy_project.py`)は`<root_dir>/project/`を見る。そのため実験用のプロジェクトは
  `Project/TEST_PROJECT_##/project/`の下に置く形になり、`apps/sample_project/`(`project/`の階層が無い)とそろわない。
- 現行の`Project`は開くときに`scene/`の原稿をすべて読み、1つでも読めないと、それ以降の原稿を読まずに進む。
  `main.py`は各場面の原稿をファイルから読み直すので影響しないが、`project.acts`は当てにできない。

## 技術的負債

- `Project`が2つある: `core/service/process/production/_legacy_project.py`(ドラマ用。ディレクトリ・人物・場面の読み込みと生成器の保持)と
  `core/project/project.py`(QIDM由来)。
- `core/schema/formats/_legacy_drama.py`(旧`core/model/drama.py`。新しいモデルに移ったら削除する):
  - 声の一覧`GeminiVoice`(提供元に依存するもの)がドラマのモデルに入っている。
  - `Actor`がフィールドと同名のproperty(`character_name`・`label`・`gender`)を定義している(実害は無いが不要)。
- `core/prompt/drama_production/sound.py`が`core/schema/formats/_legacy_drama.py`(`Transcript`)をimportしている。`prompt`は
  `genai.prompt`と`model`だけを使う決まり([architecture.md](architecture.md) 1.1)に反する。旧モデルを削除するときに解消する。
- 読み込みの失敗を`print`で知らせて処理を続ける(`core/service/process/production/_legacy_project.py`)。
- `Project`の設定(`core/project/project.py`の`llm`・`tts`)は、まだ制作の流れ(`main.py`)が使っていない。
  `main.py`は提供元・モデル名を自分で持って生成器を作る(APIキーだけは`~/.aidc/secrets.env`の保存済みのものを使う)。
- `core/prompt/reference_search.py`の「発言から検索語を作る」指示(`SEARCH_TERMS_INSTRUCTIONS`)は、QIDMのモデル作成
  (Domain・Feature・Factor)向けの文面のまま。使うのは対話方式の制作から(まだ使っていない)。
- ruffの指摘が22件ある(`ruff check core api tests main.py`、2026-09-30)。15件は旧`lib/`から移したコード(`_legacy_drama.py`・
  `_legacy_project.py`の`List`・`Dict`等の古い型の書き方・importの並び・同名のproperty)、ほかは`main.py`とテスト2件のimportの並び、
  QIDMにも元からあるもの(`B905`・`F541`・`UP042`)。
