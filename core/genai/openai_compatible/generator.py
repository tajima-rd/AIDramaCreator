# core/genai/openai_compatible/generator.py
"""
OpenAI互換のchat/completions APIを持つサーバー(llama.cppのllama-server・Ollama・
Open WebUI等)による文章生成と、embeddings APIによる埋め込み(genai.generatorの抽象の具象)。

サーバーごとの違い(エンドポイントのパス・APIキーの要否)はgenai.factoryが持つ。
構造化出力はresponse_formatのjson_schemaで要求する。音声合成は無い。
"""

import base64
from typing import Optional, Union

import requests

from ..generator import (
    Attachment,
    EmbeddingConfig,
    EmbeddingGenerator,
    EmbeddingPurpose,
    Message,
    OutputTruncatedError,
    PromptInput,
    StructuredT,
    TextConfig,
    TextGenerator,
    instruction_text,
    to_messages,
)
from ..prompt import Prompt

DEFAULT_CHAT_COMPLETIONS_PATH = "/v1/chat/completions"
DEFAULT_EMBEDDINGS_PATH = "/v1/embeddings"


def _endpoint_url(api_url: str, path: str, endpoint: str) -> str:
    """サーバーのURL(http://localhost:8080)にpathを付ける。エンドポイントまで含むURLはそのまま使う。"""
    api_url = api_url.rstrip("/")
    if api_url.endswith(endpoint):
        return api_url
    return api_url + path


def chat_completions_url(api_url: str, path: str = DEFAULT_CHAT_COMPLETIONS_PATH) -> str:
    return _endpoint_url(api_url, path, "/chat/completions")


def embeddings_url(api_url: str, path: str = DEFAULT_EMBEDDINGS_PATH) -> str:
    return _endpoint_url(api_url, path, "/embeddings")


def _auth_headers(api_key: Optional[str]) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _content(message: Message) -> Union[str, list[dict]]:
    """添付の無いメッセージは文字列、添付があればOpenAI形式の部品の列にする。

    画像はdata URIで渡す(サーバーが画像に対応している場合のみ働く)。テキストのファイルは
    本文として埋め込む。それ以外(PDF等)は扱えないためValueError。
    """
    if not message.attachments:
        return message.text
    parts: list[dict] = []
    for a in message.attachments:
        if a.mime_type.startswith("image/"):
            data = base64.b64encode(a.data).decode("ascii")
            parts.append({"type": "image_url", "image_url": {"url": f"data:{a.mime_type};base64,{data}"}})
        elif a.mime_type.startswith("text/"):
            parts.append({"type": "text", "text": a.data.decode("utf-8")})
        else:
            raise ValueError(f"OpenAI互換のサーバーには添付できないファイルの種類です: {a.mime_type}")
    parts.append({"type": "text", "text": message.text})
    return parts


def build_messages(messages: list[Message], system_instruction: Optional[str]) -> list[dict]:
    result = [{"role": "system", "content": system_instruction}] if system_instruction else []
    result += [{"role": m.role, "content": _content(m)} for m in messages]
    return result


class OpenAiCompatibleTextGenerator(TextGenerator):
    # 手元のGPU/CPUで動かすことが多いため、長い生成に備えて待ち時間を長めにとる
    timeout_seconds = 600

    def __init__(
        self,
        api_url: str,
        model_name: str,
        api_key: Optional[str] = None,
        config: Optional[TextConfig] = None,
        path: str = DEFAULT_CHAT_COMPLETIONS_PATH,
    ):
        super().__init__(model_name, config)
        self.url = chat_completions_url(api_url, path)
        self.headers = _auth_headers(api_key)

    def accepts_attachment(self, mime_type: str) -> bool:
        # 画像(サーバーのモデルが対応している場合)とテキストだけ(_content参照)
        return mime_type.startswith(("image/", "text/"))

    def build_payload(
        self,
        messages: list[Message],
        system_instruction: Optional[Union[str, Prompt]],
        schema: Optional[type[StructuredT]] = None,
    ) -> dict:
        c = self.config
        # 他の提供元の機能は黙って無視せず、指定されたらエラーにする(Gemma等と同じ扱い)
        if c.thinking_level is not None:
            raise ValueError("OpenAI互換のサーバーでは思考レベル(thinking_level)を指定できません。")
        if c.use_url_context:
            raise ValueError("OpenAI互換のサーバーではURLの読み込み(use_url_context)を使えません。")
        payload = {
            "model": self.model_name,
            "messages": build_messages(messages, instruction_text(system_instruction)),
            "stream": False,
        }
        for key, value in (
            ("temperature", c.temperature),
            ("top_p", c.top_p),
            ("top_k", c.top_k),
            ("max_tokens", c.max_output_tokens),
        ):
            if value is not None:
                payload[key] = value
        if schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": schema.__name__, "schema": schema.model_json_schema(), "strict": True},
            }
        return payload

    def _post(self, payload: dict) -> dict:
        response = requests.post(self.url, headers=self.headers, json=payload, timeout=self.timeout_seconds)
        response.raise_for_status()
        return response.json()

    def _complete(self, payload: dict) -> str:
        return self._post(payload)["choices"][0]["message"]["content"] or ""

    def generate(
        self,
        prompt: PromptInput,
        *,
        system_instruction: Optional[Union[str, Prompt]] = None,
        attachments: Optional[list[Attachment]] = None,
    ) -> str:
        payload = self.build_payload(to_messages(prompt, attachments), system_instruction)
        return self._complete(payload).strip()

    def generate_structured(
        self,
        prompt: PromptInput,
        schema: type[StructuredT],
        *,
        system_instruction: Optional[Union[str, Prompt]] = None,
        attachments: Optional[list[Attachment]] = None,
    ) -> StructuredT:
        payload = self.build_payload(to_messages(prompt, attachments), system_instruction, schema)
        body = self._post(payload)
        choice = body["choices"][0]
        message = choice.get("message") or {}
        if choice.get("finish_reason") == "length":
            # 思考(reasoning_content)が長引き、サーバーの文脈長に達して答えのJSONが途中で切れた
            # (Qwen3.8-27B・llama.cppで確認)。不正なJSONの誤りにせず、原因が分かる誤りにする
            tokens = (body.get("usage") or {}).get("completion_tokens")
            reasoning = len(message.get("reasoning_content") or "")
            raise OutputTruncatedError(
                "生成AIの出力が長さの上限に達して途中で切れました"
                f"(出力{tokens if tokens is not None else '?'}トークン、うち思考{reasoning}字)。"
                "思考が長すぎた可能性があります。送り直すと通ることがあります。続く場合はサーバーの文脈長"
                "(llama.cppの-c)または出力の上限を大きくしてください。"
            )
        return schema.model_validate_json(message.get("content") or "")


class OpenAiCompatibleEmbeddingGenerator(EmbeddingGenerator):
    """embeddings API({"model", "input": [...]} → {"data": [{"index", "embedding"}]})による埋め込み。

    llama.cppはllama-serverを埋め込みを有効にして(--embeddings)起動し、埋め込み用のモデルを
    読み込んでおく必要がある。役割(文書/問い)の区別はEmbeddingConfigの接頭辞で行う。
    """

    timeout_seconds = 600
    batch_size = 32  # 1回のリクエストで送る文章の数(サーバーの一括処理の上限に掛からないよう控えめに)

    def __init__(
        self,
        api_url: str,
        model_name: str,
        api_key: Optional[str] = None,
        config: Optional[EmbeddingConfig] = None,
        path: str = DEFAULT_EMBEDDINGS_PATH,
    ):
        super().__init__(model_name, config)
        self.url = embeddings_url(api_url, path)
        self.headers = _auth_headers(api_key)

    def build_payload(self, texts: list[str]) -> dict:
        payload: dict = {"model": self.model_name, "input": texts}
        if self.config.dimensions is not None:
            payload["dimensions"] = self.config.dimensions
        return payload

    def embed_texts(self, texts: list[str], purpose: EmbeddingPurpose) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            response = requests.post(
                self.url, headers=self.headers, json=self.build_payload(batch), timeout=self.timeout_seconds
            )
            response.raise_for_status()
            data = sorted(response.json()["data"], key=lambda item: item.get("index", 0))
            vectors += [item["embedding"] for item in data]
        return vectors
