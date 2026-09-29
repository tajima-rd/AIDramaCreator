# core/prompt/drama_production/scene.py
"""
原稿の生成(script/の台詞 → scene/の演出付きの原稿YAML)のプロンプト。
"""

from core.genai.prompt import (
    BulletInstruction,
    ForbiddenRule,
    MandatoryRule,
    OutputFormat,
    Prompt,
    Section,
    StepInstruction,
    TextBlock,
)


def generate_transcript_prompt(character_map: list[list[str]], dialog: str) -> str:
    """
    引数のキャラクターマップ（任意の人数）と原稿テキストを組み込み、
    完全にコンポーネント指向で構造化されたプロンプト文字列を生成して返却する。

    scene_idはシステムが決めるため、生成AIには書かせない(scene_generatorが付ける)。出力例は
    記入欄(<…>)だけにする。具体的な値を書くと、生成AIがそれを写す(title・contextが例と同じになった)。
    """

    role_desc = (
        "あなたは優秀な音声ドラマのディレクターであり、スクリプトエディターです。\n"
        "提供された日本語の対話原稿を分析し、指定されたYAMLフォーマットに完全に変換して出力してください。"
    )

    yaml_template = (
        "title: \"<この場面のタイトル(英語)>\"\n"
        "transcripts:\n"
        "  - actor_name: \"<キャラクターのマッピングで置き換えたactor_name>\"\n"
        "    context: \"<場所・状況(英語)>\"\n"
        "    scene: \"<動き・表情(英語)>\"\n"
        "    directors_note:\n"
        "      style: \"<話し方(英語)>\"\n"
        "      pace: \"<Moderate / Fast / Slow のいずれか>\"\n"
        "    text: \"<原稿の台詞に音声感情タグを加えたもの>\"\n"
        "    order: 1\n"
        "  # 以下、原稿の台詞1つにつき1項目を、原稿の順に続ける"
    )

    # キャラクターマッピングの動的生成
    mapping_lines = []

    # zipは使わず、リストから直接 [input_name, actor_name] を分解して取り出す
    for input_name, actor_name in character_map:
        mapping_lines.append(f"「{input_name}」 ➡ actor_name: \"{actor_name}\"")

    # プロンプトツリーの構築（ご提示いただいた理想的な構造）
    prompt_instance = Prompt(components=[
        
        Section(title="システム定義", children=[
            Section(title="役割", children=[
                TextBlock(role_desc)
            ]),
            Section(title="出力仕様と絶対ルール", children=[
                MandatoryRule(
                    BulletInstruction(items=[
                        "出力は、必ずマークダウンのコードブロック（```yaml から ``` まで）の中にすべて含めてください。",
                        "完全なYAMLのみを出力してください。",
                        "出力仕様の <…> は記入欄です。<…> の文言を写さず、原稿の内容から書いてください。"
                    ])
                ),
                ForbiddenRule(
                    BulletInstruction(items=[
                        "コードブロックの前後には、挨拶、解説、説明などの余計なテキストを一切出力しないでください。"
                    ])
                ),
                OutputFormat(format_type="YAML", template=yaml_template)
            ])
        ]),

        Section(title="変換・演出ルール", children=[
            StepInstruction(steps=[
                f"キャラクターのマッピング:\n   原稿の登場人物を、以下のように機械的に置き換えてください。\n" + "\n".join([f"   - {line}" for line in mapping_lines]),
                "音声感情タグの挿入:\n   セリフ（transcript）の適切だと思う場所（文頭や文末、感情の変化点）に、以下のタグを必ず散りばめてください。\n   [amazed], [crying], [curious], [excited], [sighs], [gasp], [giggles], [laughs], [mischievously], [panicked], [sarcastic], [serious], [shouting], [tired], [trembling], [whispers], [very_fast], [very_slow]\n   ※1つのセリフに複数入れても構いません。",
                "演出指示（directors_note / scene）の補完:\n   原稿のトーンやセリフの内容から読み取れる「場所・状況（context）」「動き（scene）」「話し方（style）」「速度（pace: Moderate/Fast/Slow）」を推測し、英語で具体的に記述してください。",
                "順序（order）:\n   1 から始まる連番にしてください。"
            ])
        ]),

        Section(title="入力データ", children=[
            Section(title="変換対象の原稿", children=[
                TextBlock(dialog)
            ])
        ])
    ])

    return prompt_instance.to_text()
