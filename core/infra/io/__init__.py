# core/infra/io/__init__.py
"""
外部とのやり取りの形式(ユーザーが持ち込む/持ち出すファイル)と、ドラマの構成要素(core.model)との
相互変換。DBには触れない。docs/architecture.md 1.1節参照。

- model_definition_reader・model_definition_writer: モデル定義YAML(core.schema.formats.dramaturgy_definition)と
  Dramaturgyの相互変換(1ファイル・分割のどちらも)
"""
