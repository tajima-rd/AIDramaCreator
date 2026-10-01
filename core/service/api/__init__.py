# core/service/api/__init__.py
"""
システムの公開API(インターフェース非依存)。

HTTP(api/)・ネイティブGUI・CLI等どのインターフェースからも、同じ契約でシステムを使う:
- リソースは識別子(project_id・file_id等)で受け取り、DBのパス等プロジェクト内の
  ファイル配置はここでcore.projectが解決する
- 受け取り・戻り値の両方をcore.schemaの型にする
- 概念単位のモジュールで構成し、core.schema.apiのDTOのファイル分けと対応させる

実際の処理はcore.service.process(DBのパス単位で動く内部の処理)に委ねる。
docs/architecture.md 1.1節参照。

- project: プロジェクトの作成・開く・一覧・プロパティ・保存
- preference: 生成AIの設定・APIキー・接続確認・設定の入力補助
- dataset: Dataset(参考資料等)の一覧・追加・取得・メタデータ・削除
- drama_model: 作品モデルの正本と版(読むだけ)
- drama_draft: 作品モデルの下書き(作成・中身・履歴・取り込み・Apply・直接編集・Undo・確定・破棄)
"""
