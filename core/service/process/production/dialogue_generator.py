# core/service/process/production/dialogue_generator.py
"""
台詞の生成: あらすじ+人物設定 → 台詞(script/)。
"""

from core.prompt.drama_production import generate_dialogue_prompt


def generate_dialogue(project, synopsis, profiles, output_file, num_char=350):
    prompt = generate_dialogue_prompt(synopsis, profiles, num_char=num_char)

    response_text = project.llm_gen.generate(prompt, system_instruction=project.system_instruction)

    with open(output_file, "w", encoding="utf-8") as f:
            f.write(response_text)
