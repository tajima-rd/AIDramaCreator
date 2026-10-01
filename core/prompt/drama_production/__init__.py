# core/prompt/drama_production
"""
制作の流れ(docs/overview.md「制作の流れ」)の各工程のプロンプト。

- dialogue: あらすじ+人物設定 → 台詞(人物設定は、character/*.txtの文章か、Characterから組み立てたもの)
- scene: 台詞 → 演出付きの原稿YAML
- sound: 原稿の1台詞 → 音声合成への指示
"""

from .dialogue import character_profile, generate_dialogue_prompt
from .scene import generate_transcript_prompt
from .sound import generate_sound_drama_prompt

__all__ = ["character_profile", "generate_dialogue_prompt", "generate_transcript_prompt", "generate_sound_drama_prompt"]
