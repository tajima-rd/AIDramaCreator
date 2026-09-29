# core/genai/audio_converter.py
"""
生成AIが返す生の音声データ(PCM)をWAVに変換する。
"""

import struct


def parse_audio_mime_type(mime_type: str) -> dict:
    """"audio/L16;rate=24000"のようなMIMEタイプから、量子化ビット数とサンプルレートを得る。"""
    bits_per_sample, rate = 16, 24000
    for param in mime_type.split(";"):
        param = param.strip().lower()
        if param.startswith("rate="):
            rate = int(param.split("=")[1])
        elif param.startswith("audio/l"):
            bits_per_sample = int(param[7:])
    return {"bits_per_sample": bits_per_sample, "rate": rate}


def pcm_to_wav(audio_data: bytes, mime_type: str) -> bytes:
    """PCM(モノラル)にWAVのヘッダーを付ける。"""
    parameters = parse_audio_mime_type(mime_type)
    bits_per_sample = parameters["bits_per_sample"]
    sample_rate = parameters["rate"]
    num_channels = 1
    data_size = len(audio_data)
    bytes_per_sample = bits_per_sample // 8
    block_align = num_channels * bytes_per_sample
    byte_rate = sample_rate * block_align
    chunk_size = 36 + data_size

    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", chunk_size, b"WAVE", b"fmt ", 16, 1,
        num_channels, sample_rate, byte_rate, block_align, bits_per_sample,
        b"data", data_size,
    )
    return header + audio_data


def is_wav(mime_type: str) -> bool:
    return mime_type.lower().split(";")[0].strip() in ("audio/wav", "audio/x-wav", "audio/wave")
