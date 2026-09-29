# core/prompt
"""
用途ごとのプロンプト(生成AIに「何を聞くか」)と、生成AIに返させる構造(pydanticのスキーマ)。

プロンプトを組み立てる部品(Section・TextBlock等)と生成器(「どう聞くか」)はcore.genaiにある。
このパッケージは生成AIを呼ばない(呼ぶのはcore.service.process)。

- drama_production/: 制作の流れ(あらすじ → 台詞 → 原稿 → 音声)の各工程のプロンプト
"""
