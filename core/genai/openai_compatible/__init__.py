# core/genai/openai_compatible
"""OpenAI互換のAPIを持つサーバー(llama.cpp・Ollama・Open WebUI等)による生成AIの具象。追加の依存は不要。"""

from .generator import OpenAiCompatibleEmbeddingGenerator, OpenAiCompatibleTextGenerator

__all__ = ["OpenAiCompatibleEmbeddingGenerator", "OpenAiCompatibleTextGenerator"]
