# 既知のバグ・技術的負債

## 不具合

- **作品があるプロジェクトへモデル定義YAMLを取り込むと、YAMLの`key`が既存の作品と重なって断られることがある**(2026-10-02発見)。
  例: 作品が1つある下書きに`apps/sample_data/令和但馬道中膝栗毛`を`import-path`(replaceなし)で重ねると、「Actのkey 'act_001' が2つあります」
  の400になる。下書きの中身の`key`は書き出すたびに種類と通し番号で振るので、別の作品の要素と同じ`key`を持つ。部分YAMLの重ね合わせは
  idが無ければ`key`で同じ要素を探すため、別の作品の幕と取り違えるか、重複として断られる(`core/infra/io/model_definition_patch.py`)。
  取り込む側のYAMLの`key`を、重ねる先と衝突しない形に扱う必要がある。

## 技術的負債

- **制作の流れ(`main.py`→`core/service/process/production/`)は、演者の声を旧来の30声の表(`GeminiVoice`)で引く**(2026-10-02)。Castsタブ・Auditionで
  新しい声の一覧から選んだ声(例: `ja-jp-advisor-1`)は「声にありません」のエラーになり、演者の`tts_provider`・`tts_model`も使わない
  (常にproject.yamlの`genai.tts`)。制作の流れを新しいモデルへ移すときに直す(`_model_definition_project.py`の`_actor`)。

- **作業補助の生成AIに手元のllama.cppを使うと、企画書の登場人物の取り込み・矛盾の確認に1回約3分かかる**(2026-10-02、Ryzen AI 7 PRO 350の内蔵GPU、
  Gemma 4 26B-A4B Q8)。原因は2つ: llama.cppがGemma 4の推論(thinking)を既定で行うこと(要求に`chat_template_kwargs: {enable_thinking: false}`を
  付ければ止まることを確かめた)と、プロンプトの読み込みが毎秒約30トークンと遅いこと(登録済みの人物の設定は約2500トークン)。`core/genai`の
  OpenAI互換の生成器は思考の指定(`TextConfig.thinking_level`)を受け付けずエラーにしている。対処(推論を止める指定を足すか等)はユーザーと相談する。
- 手元のモデルが作った人物の骨組みは、読みを漢字のまま返す・特徴の定義(Definition)の欄に説明を書く等、指示に従わないことがある(2026-10-02)。
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
