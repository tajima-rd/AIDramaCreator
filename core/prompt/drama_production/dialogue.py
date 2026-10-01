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
from core.model.drama import Character


def character_profile(character: Character) -> str:
    """
    人物(Character)を、台詞の生成に渡す人物設定の文章(Markdown)にする。旧来のcharacter/*.txtの代わり。
    人物関係は、この人物から見たもの(source)だけを書く(相手から見た関係は、相手の人物設定に書かれる)。
    """
    lines = [f"# {character.name}" + (f"（{character.reading}）" if character.reading else "")]
    lines += [f"* {label}: {value}" for label, value in (("性別", character.gender), ("年齢", character.age)) if value]
    if character.speech_style:
        lines += ["", "## 話し方", character.speech_style]
    for characteristic in character.characteristics:
        lines += ["", f"## {characteristic.item}"]
        if characteristic.definition:
            lines.append(f"（{characteristic.item}とは: {characteristic.definition}）")
        if characteristic.description:
            lines.append(characteristic.description)
        for feature in characteristic.features:
            head = f"* **{feature.item}**" + (f"（{feature.definition}）" if feature.definition else "")
            lines.append(f"{head}: {feature.value}" if feature.value else head)
            if feature.description:
                lines.append(f"  {feature.description}")
    if character.biographies:
        lines += ["", "## 経歴"]
        for biography in character.biographies:
            period = biography.period.label if biography.period.label else ""
            lines.append(f"* 【{period}】{biography.episode}")
    own = [r for r in character.relationships if r.source is character]
    if own:
        lines += ["", "## 人物関係"]
        for relationship in own:
            target = relationship.target
            name = target.name + (f"（{target.reading}）" if target.reading else "")
            period = f"【{relationship.period.label}】" if relationship.period and relationship.period.label else ""
            lines.append(f"* {period}{relationship.label}：{name}")
            if relationship.description:
                lines.append(f"  {relationship.description}")
    return "\n".join(lines)


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
