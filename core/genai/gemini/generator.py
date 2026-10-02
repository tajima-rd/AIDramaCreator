# core/genai/gemini/generator.py
"""
Google Geminiによる文章生成・音声合成・埋め込み(genai.generatorの抽象の具象)。
"""

import json
from typing import Optional, Union

import requests

from google import genai
from google.genai import types

from ..audio_converter import is_wav, pcm_to_wav
from ..generator import (
    Attachment,
    EmbeddingConfig,
    EmbeddingGenerator,
    EmbeddingPurpose,
    Message,
    OutputTruncatedError,
    PromptInput,
    SpeechConfig,
    SpeechGenerator,
    StructuredT,
    TextConfig,
    TextGenerator,
    VoiceInfo,
    instruction_text,
    parse_structured,
    to_messages,
)
from ..prompt import Prompt

DEFAULT_TEXT_MODEL = "gemma-4-31b-it"
DEFAULT_SPEECH_MODEL = "gemini-3.8-flash-lite-tts"
DEFAULT_EMBEDDING_MODEL = "gemini-embedding-2"
# 声の一覧(2026-10-02に、言語ごとの声を含めて約2,000件をページに分けて返すことを確かめた)
VOICES_URL = "https://generativelanguage.googleapis.com/v1beta/voices"
_VOICES_PAGE_SIZE = 1000

# 埋め込む文章の役割 → GeminiのtaskType
EMBEDDING_TASK_TYPES = {"document": "RETRIEVAL_DOCUMENT", "query": "RETRIEVAL_QUERY"}


def build_contents(messages: list[Message]) -> list[types.Content]:
    """メッセージ列をGeminiの会話(ロールはuser/model)にする。添付はテキストの前に置く。"""
    return [
        types.Content(
            role="model" if m.role == "assistant" else "user",
            parts=[
                *(types.Part.from_bytes(data=a.data, mime_type=a.mime_type) for a in m.attachments),
                types.Part.from_text(text=m.text),
            ],
        )
        for m in messages
    ]


def schema_in_prompt(model_name: str) -> bool:
    """構造化出力で、形(JSON Schema)をresponse_schemaで縛らずに指示の文で伝えるモデルか。

    Gemini APIのGemmaは、response_schemaで出力を縛ると、文の途中から同じ語を繰り返して出力の上限まで止まらないことがある
    (2026-10-02、gemma-4-31b-itで企画書の応答の型を渡して確認。JSONで返すことだけを指定し、形を指示の文に書くと約1分で正しく返った)。
    """
    return model_name.lower().startswith("gemma")


def schema_instruction(schema: type[StructuredT]) -> str:
    """応答の形を指示の文で伝えるときの節。"""
    return (
        "# 出力の形\n次のJSON Schemaに合うJSONだけを返す(前後に説明やコードの囲みを付けない)。\n"
        + json.dumps(schema.model_json_schema(), ensure_ascii=False)
    )


class GeminiTextGenerator(TextGenerator):
    def __init__(self, api_key: str, model_name: str = DEFAULT_TEXT_MODEL, config: Optional[TextConfig] = None):
        super().__init__(model_name, config)
        self.client = genai.Client(api_key=api_key)

    def accepts_attachment(self, mime_type: str) -> bool:
        # GeminiはPDF・画像・テキストを直接読める(Word・Excelは読めない)
        return mime_type == "application/pdf" or mime_type.startswith(("image/", "text/"))

    def build_config(
        self,
        system_instruction: Optional[Union[str, Prompt]],
        schema: Optional[type[StructuredT]] = None,
    ) -> types.GenerateContentConfig:
        c = self.config
        instruction = instruction_text(system_instruction)
        in_prompt = schema is not None and schema_in_prompt(self.model_name)
        if in_prompt:
            instruction = "\n\n".join(part for part in (instruction, schema_instruction(schema)) if part)
        return types.GenerateContentConfig(
            temperature=c.temperature,
            top_p=c.top_p,
            top_k=c.top_k,
            max_output_tokens=c.max_output_tokens,
            thinking_config=(
                types.ThinkingConfig(thinking_level=c.thinking_level.value)
                if c.thinking_level is not None else None
            ),
            tools=[types.Tool(url_context=types.UrlContext())] if c.use_url_context else None,
            system_instruction=instruction,
            response_mime_type="application/json" if schema is not None else None,
            response_schema=None if in_prompt else schema,
            # Pythonの関数をツールとして渡さないため、自動の関数呼び出しは使わない
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

    def generate(
        self,
        prompt: PromptInput,
        *,
        system_instruction: Optional[Union[str, Prompt]] = None,
        attachments: Optional[list[Attachment]] = None,
    ) -> str:
        chunks = self.client.models.generate_content_stream(
            model=self.model_name,
            contents=build_contents(to_messages(prompt, attachments)),
            config=self.build_config(system_instruction),
        )
        return "".join(chunk.text for chunk in chunks if chunk.text).strip()

    def generate_structured(
        self,
        prompt: PromptInput,
        schema: type[StructuredT],
        *,
        system_instruction: Optional[Union[str, Prompt]] = None,
        attachments: Optional[list[Attachment]] = None,
    ) -> StructuredT:
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=build_contents(to_messages(prompt, attachments)),
            config=self.build_config(system_instruction, schema),
        )
        candidates = getattr(response, "candidates", None) or []
        if candidates and candidates[0].finish_reason == types.FinishReason.MAX_TOKENS:
            raise OutputTruncatedError(
                "生成AIの出力が長さの上限に達して途中で切れました。送り直すと通ることがあります。"
            )
        return parse_structured(response.text or "", schema)


class GeminiSpeechGenerator(SpeechGenerator):
    def __init__(self, api_key: str, model_name: str = DEFAULT_SPEECH_MODEL, config: Optional[SpeechConfig] = None):
        super().__init__(model_name, config)
        self.client = genai.Client(api_key=api_key)
        self._api_key = api_key

    def list_voices(self, language_code: Optional[str] = None) -> list[VoiceInfo]:
        """GET /v1beta/voices(ページを辿ってすべて)。language_codeを渡すと、その言語の声だけ。"""
        voices: list[VoiceInfo] = []
        token: Optional[str] = None
        while True:
            params: dict[str, object] = {"page_size": _VOICES_PAGE_SIZE}
            if language_code:
                params["language_code"] = language_code
            if token:
                params["page_token"] = token
            response = requests.get(
                VOICES_URL, headers={"x-goog-api-key": self._api_key}, params=params, timeout=60
            )
            response.raise_for_status()
            body = response.json()
            voices.extend(
                VoiceInfo(
                    item["id"],
                    item.get("display_name"),
                    item.get("language_code"),
                    item.get("gender"),
                    item.get("pitch"),
                    item.get("accent"),
                    item.get("persona"),
                    item.get("context"),
                    item.get("description"),
                )
                for item in body.get("voices", [])
                if item.get("id")
            )
            token = body.get("next_page_token") or body.get("nextPageToken")
            if not token:
                return voices

    def build_config(self, voice: str) -> types.GenerateContentConfig:
        return types.GenerateContentConfig(
            temperature=self.config.temperature,
            response_modalities=["audio"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                )
            ),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

    def synthesize(self, text: Union[str, Prompt], voice: str) -> bytes:
        # 音声はストリームで分割されて届くため、PCMをつないでから1つのWAVにする。
        data = bytearray()
        mime_type = None
        for chunk in self.client.models.generate_content_stream(
            model=self.model_name,
            contents=build_contents(to_messages(text)),
            config=self.build_config(voice),
        ):
            if not chunk.parts:
                continue
            inline = chunk.parts[0].inline_data
            if inline and inline.data:
                data.extend(inline.data)
                mime_type = inline.mime_type
        if mime_type is None:
            raise ValueError("生成AIから音声データが返されませんでした。")
        return bytes(data) if is_wav(mime_type) else pcm_to_wav(bytes(data), mime_type)


class GeminiEmbeddingGenerator(EmbeddingGenerator):
    batch_size = 100  # batchEmbedContentsの1回あたりの上限

    def __init__(self, api_key: str, model_name: str = DEFAULT_EMBEDDING_MODEL, config: Optional[EmbeddingConfig] = None):
        super().__init__(model_name, config)
        self.client = genai.Client(api_key=api_key)

    def build_config(self, purpose: EmbeddingPurpose) -> types.EmbedContentConfig:
        return types.EmbedContentConfig(
            task_type=EMBEDDING_TASK_TYPES[purpose],
            output_dimensionality=self.config.dimensions,
        )

    def _embed(self, texts: list[str], purpose: EmbeddingPurpose) -> list[list[float]]:
        # 文字列の一覧をそのまま渡すと、1つの内容の複数の部分として1つの埋め込みにまとめるモデルがある
        # (gemini-embedding-2等のマルチモーダルの埋め込み。「埋め込みの数が文章の数と合いません」になった)。
        # 文章ごとにContentを分けて渡す
        response = self.client.models.embed_content(
            model=self.model_name,
            contents=[types.Content(parts=[types.Part(text=t)]) for t in texts],
            config=self.build_config(purpose),
        )
        return [list(e.values or []) for e in response.embeddings or []]

    def embed_texts(self, texts: list[str], purpose: EmbeddingPurpose) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            embeddings = self._embed(batch, purpose)
            if len(embeddings) != len(batch):
                # Contentを分けてもまとめて1つにするモデルでは、1件ずつ埋め込む
                embeddings = [e for text in batch for e in self._embed([text], purpose)]
            vectors += embeddings
        return vectors
