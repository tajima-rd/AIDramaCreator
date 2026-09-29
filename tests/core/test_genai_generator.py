"""
生成AIの抽象の契約(core.genai.generator)と、Geminiの具象(core.genai.gemini)。
実際のAPIは呼ばず、Geminiのクライアントを偽物に差し替えて、送る内容と受け取り方を確かめる。

- 文字列/Prompt/メッセージ列がメッセージ列にそろい、添付が最後のuserメッセージに付くこと
- Geminiへの会話(ロール・添付・system_instruction・設定)が正しく組み立てられること
- 構造化出力がJSONで要求され、pydanticのスキーマに詰めて返ること
- 音声がPCMの断片をつないだ1つのWAVのバイト列で返ること
"""

import struct
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from core.genai import Attachment, Message, Prompt, Section, TextBlock, TextConfig, ThinkingLevel
from core.genai.generator import to_messages

genai_types = pytest.importorskip("google.genai.types")

from core.genai.gemini import GeminiSpeechGenerator, GeminiTextGenerator  # noqa: E402
from core.genai.gemini.generator import build_contents  # noqa: E402

PDF = Attachment(data=b"%PDF-1.4", mime_type="application/pdf")


def test_to_messages():
    assert to_messages("hello") == [Message(role="user", text="hello")]

    prompt = Prompt([Section("役割", [TextBlock("x")])])
    assert to_messages(prompt, [PDF]) == [Message(role="user", text=prompt.to_text(), attachments=[PDF])]

    history = [
        Message(role="user", text="q1"),
        Message(role="assistant", text="a1"),
        Message(role="user", text="q2"),
        Message(role="assistant", text="a2"),
    ]
    messages = to_messages(history, [PDF])
    assert messages[2].attachments == [PDF]
    assert history[2].attachments == []  # 渡したメッセージ列は書き換えない

    with pytest.raises(ValueError):
        to_messages([Message(role="assistant", text="a")])


def test_attachment_from_file(tmp_path):
    path = tmp_path / "paper.pdf"
    path.write_bytes(b"%PDF-1.4")
    assert Attachment.from_file(path) == PDF
    with pytest.raises(ValueError):
        Attachment.from_file(tmp_path / "unknown.zzz_unknown")


def test_build_contents():
    contents = build_contents([
        Message(role="user", text="q", attachments=[PDF]),
        Message(role="assistant", text="a"),
    ])
    assert [c.role for c in contents] == ["user", "model"]
    assert contents[0].parts[0].inline_data.mime_type == "application/pdf"
    assert contents[0].parts[1].text == "q"


class _Schema(BaseModel):
    name: str
    value: float


class _FakeModels:
    def __init__(self, text="", chunks=()):
        self.text = text
        self.chunks = chunks
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text=self.text)

    def generate_content_stream(self, **kwargs):
        self.calls.append(kwargs)
        return iter(self.chunks)


def _text_generator(config=None, **fake):
    gen = GeminiTextGenerator(api_key="dummy-key", model_name="gemini-3.5-flash", config=config)
    gen.client = SimpleNamespace(models=_FakeModels(**fake))
    return gen


def test_text_config_defaults():
    config = _text_generator().build_config(None)
    assert config.system_instruction is None
    assert config.tools is None and config.thinking_config is None
    assert config.response_mime_type is None


def test_generate_text():
    gen = _text_generator(
        config=TextConfig(thinking_level=ThinkingLevel.HIGH, use_url_context=True),
        chunks=[SimpleNamespace(text="Hello, "), SimpleNamespace(text=None), SimpleNamespace(text="world ")],
    )
    assert gen.generate("hi", system_instruction="be brief") == "Hello, world"
    config = gen.client.models.calls[0]["config"]
    assert config.system_instruction == "be brief"
    assert config.thinking_config.thinking_level.value == "HIGH"
    assert config.tools[0].url_context is not None


def test_generate_structured():
    gen = _text_generator(text='{"name": "hazard_ratio", "value": 1.5}')
    result = gen.generate_structured("extract", _Schema, attachments=[PDF])
    assert result == _Schema(name="hazard_ratio", value=1.5)
    call = gen.client.models.calls[0]
    assert call["config"].response_mime_type == "application/json"
    assert call["config"].response_schema is _Schema
    assert call["contents"][0].parts[0].inline_data.mime_type == "application/pdf"


def test_generate_structured_truncated():
    """出力の上限で切れた(finish_reason=MAX_TOKENS)ら、不正なJSONの誤りではなくOutputTruncatedError。"""
    from google.genai import types

    from core.genai import OutputTruncatedError

    gen = _text_generator(text='{"name": "haz')
    gen.client.models.generate_content = lambda **kwargs: SimpleNamespace(
        text='{"name": "haz', candidates=[SimpleNamespace(finish_reason=types.FinishReason.MAX_TOKENS)]
    )
    with pytest.raises(OutputTruncatedError):
        gen.generate_structured("extract", _Schema)


def _audio_chunk(data, mime_type="audio/L16;codec=pcm;rate=24000"):
    part = SimpleNamespace(inline_data=SimpleNamespace(data=data, mime_type=mime_type))
    return SimpleNamespace(parts=[part])


def test_synthesize_joins_pcm_into_one_wav():
    gen = GeminiSpeechGenerator(api_key="dummy-key", model_name="gemini-3.1-flash-tts-preview")
    gen.client = SimpleNamespace(models=_FakeModels(
        chunks=[_audio_chunk(b"\x01\x00" * 3), SimpleNamespace(parts=None), _audio_chunk(b"\x02\x00" * 2)]
    ))
    wav = gen.synthesize("こんにちは", voice="Kore")
    assert wav[:4] == b"RIFF" and wav[8:12] == b"WAVE"
    sample_rate, = struct.unpack("<I", wav[24:28])
    data_size, = struct.unpack("<I", wav[40:44])
    assert sample_rate == 24000 and data_size == 10
    config = gen.client.models.calls[0]["config"]
    assert config.speech_config.voice_config.prebuilt_voice_config.voice_name == "Kore"

    gen.client = SimpleNamespace(models=_FakeModels(chunks=[]))
    with pytest.raises(ValueError):
        gen.synthesize("x", voice="Kore")
