# core/service/process/__init__.py
"""
内部の処理。公開API(core.service.api)から使う。フォルダは処理の分野、ファイル名は「対象_役割」。

- production/: 制作の流れ(あらすじ → 台詞 → 原稿 → 音声)の各工程
- edit/: プロジェクト・設定(Preferences)・Datasetの作成と更新の手順
- genai/: 生成AIを使う処理(Projectの設定からの生成器の組み立て、接続確認、設定の入力補助、参考資料の検索)
"""
