# 既知のバグ・技術的負債

## 不具合

- なし

## 技術的負債

- `core/schema/formats/_legacy_drama.py`(旧`core/model/drama.py`。新しいモデルに移ったら削除する):
  - 声の一覧`GeminiVoice`(提供元に依存するもの)がドラマのモデルに入っている。
  - `Actor`がフィールドと同名のproperty(`character_name`・`label`・`gender`)を定義している(実害は無いが不要)。
- `core/prompt/drama_production/sound.py`が`core/schema/formats/_legacy_drama.py`(`Transcript`)をimportしている。`prompt`は
  `genai.prompt`と`model`だけを使う決まり([architecture.md](architecture.md) 1.1)に反する。旧モデルを削除するときに解消する。
- `main.py`は、`system_instruction`と`TextConfig`(思考の深さ・temperature等)を直書きしている(接続先は`<root_dir>/project.yaml`の`genai`)。
- `core/prompt/reference_search.py`の「発言から検索語を作る」指示(`SEARCH_TERMS_INSTRUCTIONS`)は、QIDMのモデル作成
  (Domain・Feature・Factor)向けの文面のまま。使うのは対話方式の制作から(まだ使っていない)。
- ruffの指摘が22件ある(`ruff check core api tests main.py`、2026-09-30)。多くは旧`lib/`から移したコード(`_legacy_drama.py`の`List`等の
  古い型の書き方・importの並び・同名のproperty)、ほかはテストのimportの並び、
  QIDMにも元からあるもの(`B905`・`F541`・`UP042`)。
