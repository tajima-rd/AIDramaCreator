# core/prompt/ai_build/__init__.py
"""
Build with AI(生成AIと相談しながら作品を作るパネル。docs/architecture.md 10節)の、工程ごとのプロンプトと生成AIに返させる構造。
工程(タブ)とエージェント・タスクの対応はstep.pyのBUILD_STEPS。生成AIは呼ばない(呼ぶのはcore.service.process.genai.ai_builder)。
"""
