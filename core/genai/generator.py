# core/genai/generator.py
"""
生成AIの抽象の契約(提供元に依存しない)。

- TextGenerator: 文章生成。文字列/Prompt/メッセージ列を受け取り、文字列(generate)か、
  pydanticのスキーマに詰めた値(generate_structured)を返す
- SpeechGenerator: 音声合成。WAVのバイト列を返す(保存は呼び出し側)
- EmbeddingGenerator: 埋め込み。文章の列を同じ長さのベクトルの列にする(資料の検索、rag/)
- Message・Attachment: 会話のメッセージと、それに添付するファイル(PDF等)
- TextConfig・SpeechConfig・EmbeddingConfig: 生成の設定

具象(提供元ごとの実装)はサブパッケージ(gemini/・openai_compatible/)に置き、factoryが
提供元の名前(client)に応じて選ぶ。この層はサブパッケージを使わない。
"""

import abc
import mimetypes
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Literal, Optional, TypeVar, Union

from pydantic import BaseModel

from .prompt import Prompt

StructuredT = TypeVar("StructuredT", bound=BaseModel)


class OutputTruncatedError(RuntimeError):
    """生成AIの出力が長さの上限(出力の上限・サーバーの文脈長)に達して途中で切れた。

    構造化出力では、切れたJSONが不正なJSONの誤りになり原因が分からないため、これで区別する。
    思考する(reasoning)モデルは思考の長さが毎回違うため、送り直すと通ることがある。"""


class ThinkingLevel(Enum):
    """推論にかける手間。Noneなら提供元の既定。"""

    MINIMAL = "MINIMAL"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass(frozen=True)
class Attachment:
    """メッセージに添付するファイル(論文のPDF・画像等)。"""

    data: bytes
    mime_type: str

    @classmethod
    def from_file(cls, path: Union[str, Path], mime_type: Optional[str] = None) -> "Attachment":
        path = Path(path)
        mime_type = mime_type or mimetypes.guess_type(path.name)[0]
        if mime_type is None:
            raise ValueError(f"ファイルの種類(MIMEタイプ)を判別できません: {path}")
        return cls(data=path.read_bytes(), mime_type=mime_type)


@dataclass
class Message:
    """会話の1メッセージ。roleはuser(利用者)かassistant(生成AI)。"""

    role: Literal["user", "assistant"]
    text: str
    attachments: list[Attachment] = field(default_factory=list)


@dataclass(frozen=True)
class TextConfig:
    """文章生成の設定。Noneの項目は提供元の既定に任せる。"""

    temperature: Optional[float] = 0.7
    top_p: Optional[float] = 0.95
    top_k: Optional[int] = None
    max_output_tokens: Optional[int] = None
    thinking_level: Optional[ThinkingLevel] = None
    # 本文中のURLの中身を生成AIに読ませる(提供元が対応している場合)
    use_url_context: bool = False


@dataclass(frozen=True)
class SpeechConfig:
    """音声合成の設定。"""

    temperature: Optional[float] = 1.0


# 埋め込む文章の役割。検索される側(資料の断片)か、検索する側(問い)か
EmbeddingPurpose = Literal["document", "query"]


@dataclass(frozen=True)
class EmbeddingConfig:
    """埋め込みの設定。

    dimensionsは出力するベクトルの長さ(提供元が対応していれば。Noneならモデルの既定)。
    document_prefix/query_prefixは、役割を文章の先頭の決まった文字列で区別するモデル
    (例: "search_document: "・"search_query: ")のためのもので、役割を引数で受け取る提供元
    (GeminiのtaskType)では空のままでよい。
    """

    dimensions: Optional[int] = None
    document_prefix: str = ""
    query_prefix: str = ""


PromptInput = str | Prompt | list[Message]


def to_messages(prompt: PromptInput, attachments: Optional[list[Attachment]] = None) -> list[Message]:
    """文字列/Prompt/メッセージ列を、メッセージ列にそろえる。

    attachmentsは、文字列/Promptの場合はそのメッセージに、メッセージ列の場合は最後の
    userメッセージに添付する。
    """
    if isinstance(prompt, (str, Prompt)):
        text = prompt.to_text() if isinstance(prompt, Prompt) else prompt
        return [Message(role="user", text=text, attachments=list(attachments or []))]

    messages = list(prompt)
    if not any(m.role == "user" for m in messages):
        raise ValueError("メッセージ列に 'user' のメッセージがありません。")
    if attachments:
        index = max(i for i, m in enumerate(messages) if m.role == "user")
        last = messages[index]
        messages[index] = Message(
            role=last.role, text=last.text, attachments=[*last.attachments, *attachments]
        )
    return messages


class TextGenerator(abc.ABC):
    """文章生成の抽象。"""

    def __init__(self, model_name: str, config: Optional[TextConfig] = None):
        self.model_name = model_name
        self.config = config if config is not None else TextConfig()

    def accepts_attachment(self, mime_type: str) -> bool:
        """このファイルの種類をAttachmentとしてそのまま渡せるか。渡せなければ、呼び出し側が
        テキストを取り出して本文に入れる(例: 手元のLLMにPDFを渡す場合)。"""
        return False

    @abc.abstractmethod
    def generate(
        self,
        prompt: PromptInput,
        *,
        system_instruction: Optional[Union[str, Prompt]] = None,
        attachments: Optional[list[Attachment]] = None,
    ) -> str:
        """文章を生成して返す。"""

    @abc.abstractmethod
    def generate_structured(
        self,
        prompt: PromptInput,
        schema: type[StructuredT],
        *,
        system_instruction: Optional[Union[str, Prompt]] = None,
        attachments: Optional[list[Attachment]] = None,
    ) -> StructuredT:
        """schema(pydanticのモデル)の形で生成させ、検証した値を返す。

        生成AIの出力がschemaに合わなければpydantic.ValidationError。
        """


class SpeechGenerator(abc.ABC):
    """音声合成の抽象。"""

    def __init__(self, model_name: str, config: Optional[SpeechConfig] = None):
        self.model_name = model_name
        self.config = config if config is not None else SpeechConfig()

    @abc.abstractmethod
    def synthesize(self, text: Union[str, Prompt], voice: str) -> bytes:
        """textをvoice(提供元の声の名前)で読み上げ、WAVのバイト列を返す。"""


class EmbeddingGenerator(abc.ABC):
    """埋め込みの抽象。"""

    def __init__(self, model_name: str, config: Optional[EmbeddingConfig] = None):
        self.model_name = model_name
        self.config = config if config is not None else EmbeddingConfig()

    def embed(self, texts: list[str], purpose: EmbeddingPurpose = "document") -> list[list[float]]:
        """textsを同じ順・同じ数のベクトルにする。purposeに応じた接頭辞はここで付ける。"""
        if not texts:
            return []
        prefix = self.config.document_prefix if purpose == "document" else self.config.query_prefix
        vectors = self.embed_texts([prefix + t for t in texts], purpose)
        if len(vectors) != len(texts):
            raise ValueError(f"埋め込みの数が文章の数と合いません({len(vectors)}件/{len(texts)}件)。")
        return vectors

    @abc.abstractmethod
    def embed_texts(self, texts: list[str], purpose: EmbeddingPurpose) -> list[list[float]]:
        """提供元ごとの埋め込み(texts・戻り値は同じ順)。"""


def instruction_text(system_instruction: Optional[Union[str, Prompt]]) -> Optional[str]:
    """system_instructionを文字列にそろえる(空ならNone)。"""
    if isinstance(system_instruction, Prompt):
        system_instruction = system_instruction.to_text()
    return system_instruction or None
