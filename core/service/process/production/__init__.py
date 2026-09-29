# core/service/process/production
"""
制作の流れ(docs/overview.md「制作の流れ」)の各工程。現状は各工程を生成AIへの1回の依頼(ワンショット)で行う。

- dialogue_generator: あらすじ+人物設定 → 台詞(script/)
- scene_generator: 台詞 → 演出付きの原稿YAML(scene/)
- sound_generator: 原稿 → 音声(sound/のmp3)
"""

from .dialogue_generator import generate_dialogue
from .scene_generator import generate_scene
from .sound_generator import generate_sound_drama

__all__ = ["generate_dialogue", "generate_scene", "generate_sound_drama"]
