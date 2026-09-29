# core/genai
"""
生成AIによる文章生成・音声合成。

他のプロジェクトでも使えるよう(将来は独立したリポジトリで管理する)、このパッケージの外
(使う側のcore.project・core.infra等)をimportしない。どのプロジェクトの設定・APIキーを使うかは
使う側が決め、値としてfactoryに渡す(tests/core/test_genai_independence.pyで確かめる)。

- generator: 提供元に依存しない抽象の契約(TextGenerator・SpeechGenerator・EmbeddingGenerator)と、
  メッセージ・添付・設定の型
- prompt: プロンプトを部品(Section・TextBlock・MandatoryRule等)の組み合わせで作る仕組み
- factory: 提供元の名前・モデル・接続先・APIキーの値から具象の生成器を作る
- audio_converter: 生の音声データ(PCM)のWAV化
- character_check: 生成AIの出力の疑わしい文字の判定(文字の種類と、出典に現れるかの照合)
- gemini/: Google Geminiの具象(google-genaiが必要。ここではimportしない)
- openai_compatible/: OpenAI互換のAPIを持つサーバー(llama.cpp・Ollama・Open WebUI)の具象。文章生成・埋め込み
- rag/: 資料の検索(テキスト化・分割・索引・語と埋め込みによる検索・文脈の組み立て)
"""

from .factory import create_embedding_generator, create_speech_generator, create_text_generator
from .generator import (
    Attachment,
    EmbeddingConfig,
    EmbeddingGenerator,
    Message,
    OutputTruncatedError,
    SpeechConfig,
    SpeechGenerator,
    TextConfig,
    TextGenerator,
    ThinkingLevel,
)
from .prompt import (
    BulletInstruction,
    ForbiddenRule,
    MandatoryRule,
    OutputFormat,
    Prompt,
    PromptComponent,
    Section,
    StepInstruction,
    TextBlock,
)

__all__ = [
    "create_embedding_generator",
    "create_speech_generator",
    "create_text_generator",
    "Attachment",
    "EmbeddingConfig",
    "EmbeddingGenerator",
    "Message",
    "OutputTruncatedError",
    "SpeechConfig",
    "SpeechGenerator",
    "TextConfig",
    "TextGenerator",
    "ThinkingLevel",
    "BulletInstruction",
    "ForbiddenRule",
    "MandatoryRule",
    "OutputFormat",
    "Prompt",
    "PromptComponent",
    "Section",
    "StepInstruction",
    "TextBlock",
]
