# core/service/process/production/sound_generator.py
"""
音声の生成: 原稿(Scene) → 台詞ごとに音声合成して連結 → sound/<scene_id>.mp3。
連結とmp3への書き出しにpydub(ffmpeg)を使う。
"""

import io
import os

from pydub import AudioSegment

from core.model import Project, Scene
from core.prompt.drama_production import generate_sound_drama_prompt


def generate_sound_drama(project: Project, scene: Scene):
    print(f"Starting Scene [{scene.scene_id}]: {scene.title}")

    sound_dir = project.get_working_path("sound_path")
    final_filename = f"{scene.scene_id}.mp3"
    final_path = os.path.join(sound_dir, final_filename)

    combined_audio = AudioSegment.empty()

    sorted_transcript = sorted(scene.transcript, key=lambda p: p.order)

    for transcript in sorted_transcript:
        voice_name = transcript.actor.voice_name
        prompt = generate_sound_drama_prompt(transcript)

        wav = project.tts_gen.synthesize(prompt, voice=voice_name)
        combined_audio += AudioSegment.from_wav(io.BytesIO(wav))

    combined_audio.export(final_path, format="mp3")
    print(f"\nSUCCESS: Final combined audio saved to: {final_path}")
