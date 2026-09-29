# core/prompt/drama_production/dialogue.py
"""
台詞の生成(plot/のあらすじ+character/の人物設定 → script/の台詞)のプロンプト。
"""

from core.genai.prompt import (
    BulletInstruction,
    ForbiddenRule,
    MandatoryRule,
    OutputFormat,
    Prompt,
    Section,
    TextBlock,
)


def generate_dialogue_prompt(synopsis_text: str, profiles: list[list[str]], num_char: int = 350) -> str:

    profile_blocks = []

    # zipは使わず、リストから直接 [input_name, actor_name] を分解して取り出す
    for character, profile in profiles:
        profile_blocks.append(TextBlock(f"[{character}]:```\n{profile}\n```"))


    # 1. 役割の定義
    role_desc = (
        "与えられた[登場人物のキャラクタープロファイル]と[あらすじ]からキャラクター同士の自然な掛け合い（セリフ）を創作するシナリオライターです。\n"
        "AI Studioなどでそのまま再生・流し込みができるよう、完全にセリフテキストのみで構成された美しい会話劇を出力してください。"
    )

    # 2. 期待する出力フォーマットのテンプレート
    output_template = (
        'キャラクターA：セリフ。\n'
        'キャラクターB：セリフ。\n'
        'キャラクターA：セリフ。\n'
        '※「キャラクター名：」で始まり、セリフが続く形式を維持してください。'
    )

    # 3. コンポーネントツリーの構築 (prompt.py の仕様に完全準拠)
    prompt_instance = Prompt(
        components=[
            # --- 第1セクション: システム定義 ---
            Section(
                title="システム定義",
                children=[
                    Section(title="役割", children=[TextBlock(role_desc)]),
                    Section(
                        title="出力仕様と絶対ルール",
                        children=[
                            # 絶対に守らせたいルール群
                            MandatoryRule(
                                BulletInstruction(
                                    items=[
                                        "ストーリーの主軸は「あらすじ」にしたがってください。別の話は混ぜないでください。",
                                        "「ト書き」「状況説明」「(ため息をつく)」などのカッコ書きのアクションは、一切出力しないでください。",
                                        "出力は、完全に「キャラクター名：セリフ」の形式のみとしてください。",
                                        "空行（改行）を適度に入れ、読みやすい会話劇にしてください。",
                                        "与えられた「登場人物のキャラクタープロファイル」を元に、セリフの口調に深く反映させてください。",
                                        f"文字数は全体で{num_char}文字となるように出力してください。"
                                    ]
                                )
                            ),
                            # 絶対にやらせたくないルール群
                            ForbiddenRule(
                                BulletInstruction(
                                    items=[
                                        "セリフの前後や、出力の冒頭・末尾に、挨拶、解説、補足説明などの余計なテキストを絶対に含めないでください。",
                                        "「登場人物のキャラクタープロファイル」はあくまで、登場人物の背景設定です。「あらすじ」に混ぜないでください。"
                                    ]
                                )
                            ),
                            # 出力フォーマットの明示
                            OutputFormat(
                                format_type="text", template=output_template
                            ),
                        ],
                    ),
                ],
            ),
            # --- 第2セクション: 入力データ ---
            Section(
                title="入力データ",
                children=[
                    Section(
                        title="変換対象のあらすじ",
                        children=[TextBlock(synopsis_text)],
                    ),
                    Section(
                        title="登場人物のキャラクタープロファイル",
                        children=profile_blocks
                    )
                ],
            ),
        ]
    )

    # 構造化されたプロンプトテキストを返却
    return prompt_instance.to_text()
