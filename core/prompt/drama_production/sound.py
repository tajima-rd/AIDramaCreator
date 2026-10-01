# core/prompt/drama_production/sound.py
"""
音声の生成(scene/の原稿の1台詞 → 音声合成への指示)のプロンプト。
"""

from core.genai.prompt import BulletInstruction, Prompt, Section, TextBlock
from core.schema.formats._legacy_drama import Transcript


def generate_sound_drama_prompt(transcript: Transcript) -> str:
    """
    prompt.py のコンポーネント指向設計に基づき、
    オーディオプロファイルとディレクション指示のプロンプトを動的に構造化して生成します。
    """
    # -----------------------------------------------------------------
    # 1. 前処理（動的な文字列の制御）
    # -----------------------------------------------------------------
    # Personality Description
    pers_desc = transcript.actor.personality_description if transcript.actor.personality_description else ""
    
    # Style / Dynamics のリスト構築
    style_items = [transcript.directors_note.style]
    if transcript.directors_note.dynamics:
        style_items.append(f"Dynamics: {transcript.directors_note.dynamics}")
        
    # Pace と Accent のテキストブロック化
    pace_text = f"Pace: {transcript.directors_note.pace}"
    accent_text = f"Accent: {transcript.actor.accent}"

    # -----------------------------------------------------------------
    # 2. コンポーネントツリーの構築
    # -----------------------------------------------------------------
    prompt_instance = Prompt(components=[
        
        # ## "パーソナリティタイトル" と説明(モデル定義YAMLの配役には無いので、無ければ名前だけ)
        Section(title=f"AUDIO PROFILE: {transcript.actor.character_name}", children=[
            Section(title=f'"{transcript.actor.personality_title}"', children=[
                TextBlock(pers_desc)
            ]) if pers_desc else TextBlock(f'"{transcript.actor.personality_title}"')
        ] if transcript.actor.personality_title else []),

        # 場面設定
        Section(title=f"THE SCENE: {transcript.context}", children=[
            TextBlock(transcript.scene_description)
        ]),

        # ディレクターズノート
        Section(title="DIRECTOR'S NOTES", children=[
            Section(title="Style", children=[
                BulletInstruction(items=style_items)
            ]),
            TextBlock(pace_text),
            TextBlock(accent_text),
            
            # 実際の原稿・セリフ
            Section(title="TRANSCRIPT", children=[
                TextBlock(transcript.text)
            ])
        ])
    ])

    # 完全に構造化されたマークダウン文字列を返却
    return prompt_instance.to_text()
