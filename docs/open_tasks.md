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

- [ ] `core/model/`のドラマの構成要素の再定義
- [ ] Projectの作り直し(Dataset・drafts/を含む)
- [ ] SQLiteの用途と構造
- [ ] インターフェース(保留。GUIはQIDMの`apps/QIDM`を参考にする。準備の5項目は future_design.md「GUIで扱う制作の準備」)
- [ ] 対話方式の制作(保留。パッケージの移行が終わってから)
