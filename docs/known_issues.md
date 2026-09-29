# 既知のバグ・技術的負債

## 不具合

- 現行の`Project`(`core/model/project.py`)は`<root_dir>/project/`を見る。そのため実験用のプロジェクトは
  `Project/TEST_PROJECT_##/project/`の下に置く形になり、`apps/sample_project/`(`project/`の階層が無い)とそろわない。
- 現行の`Project`は開くときに`scene/`の原稿をすべて読み、1つでも読めないと、それ以降の原稿を読まずに進む。
  `main.py`は各場面の原稿をファイルから読み直すので影響しないが、`project.acts`は当てにできない。

## 技術的負債

- `Project`が2つある: `core/model/project.py`(ドラマ用。ディレクトリ・人物・場面の読み込みと生成器の保持)と
  `core/project/project.py`(QIDM由来)。
- `core/model/project.py`が`core.genai`をimportし、生成器(`llm_gen`・`tts_gen`)を持っている。
  依存方向(A→`genai`の禁止、[architecture.md](architecture.md) 1.1)に反する。Projectの作り直しで解消する。
- `core/model/drama.py`:
  - 声の一覧`GeminiVoice`(提供元に依存するもの)がドラマのモデルに入っている。
  - `Actor`がフィールドと同名のproperty(`character_name`・`label`・`gender`)を定義している(実害は無いが不要)。
- 読み込みの失敗を`print`で知らせて処理を続ける(`core/model/project.py`)。
- 空のファイル: `core/model/factory.py`。
- `Project`の設定(`core/project/project.py`の`llm`・`tts`)は、まだ制作の流れ(`main.py`)が使っていない。
  `main.py`は提供元・モデル名を自分で持って生成器を作る(APIキーだけは`~/.aidc/secrets.env`の保存済みのものを使う)。
- `core/prompt/reference_search.py`の「発言から検索語を作る」指示(`SEARCH_TERMS_INSTRUCTIONS`)は、QIDMのモデル作成
  (Domain・Feature・Factor)向けの文面のまま。使うのは対話方式の制作から(まだ使っていない)。
- ruffの指摘が32件ある(`ruff check core api tests main.py`、2026-09-29)。ほとんどは旧`lib/`から移したコード
  (`core/model/`・`core/prompt/drama_production/`)の型注釈の古い書き方等で、残りの4件はQIDMにも元からあるもの。
