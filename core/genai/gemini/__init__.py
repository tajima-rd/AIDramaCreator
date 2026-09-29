# core/genai/gemini
"""
Google Geminiによる生成AIの具象。生成器(generator。文章生成・音声合成・埋め込み)はgoogle-genai(requirements/genai.txt)が必要。
モデル名の一覧(model_lister)はREST APIを直接使い、google-genaiが無くても使えるよう、生成器は
使われたときに初めてimportする。
"""

__all__ = ["GeminiEmbeddingGenerator", "GeminiSpeechGenerator", "GeminiTextGenerator"]


def __getattr__(name):
    if name in __all__:
        from . import generator

        return getattr(generator, name)
    raise AttributeError(name)
