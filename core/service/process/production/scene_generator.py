# core/service/process/production/scene_generator.py
"""
原稿の生成: 台詞 → 演出付きの原稿YAML(scene/)。生成した原稿はプロジェクトにも読み込む。

scene_idはシステムが決める値なので、生成AIの出力ではなく引数で付ける(ファイル名・原稿の中身・
読み込んだ後の識別子をそろえるため)。
"""

import copy
import re

import yaml

from core.prompt.drama_production import generate_transcript_prompt


def generate_scene(project, scene_id, dialog, output_file):
    character_map = project.get_character_map()

    prompt = generate_transcript_prompt(character_map=character_map, dialog=dialog)

    response_text = project.llm_gen.generate(prompt, system_instruction=project.system_instruction)
    cleaned_text = re.sub(
        r"^```yaml\s*$\n|^```\s*$\n?", "", response_text, flags=re.MULTILINE
    )

    scene_data = yaml.safe_load(cleaned_text)
    if not isinstance(scene_data, dict):
        raise ValueError(f"原稿がYAMLの辞書になっていません: {type(scene_data).__name__}")
    # scene_idを先頭に置く
    scene_data = {"scene_id": scene_id, **{k: v for k, v in scene_data.items() if k != "scene_id"}}

    with open(output_file, "w", encoding="utf-8") as f:
        yaml.safe_dump(scene_data, f, allow_unicode=True, sort_keys=False)

    # load_scenes_yamlは渡した辞書を書き換えるため複製を渡す。原稿が不正ならここで例外になる
    project.load_scenes_yaml(copy.deepcopy(scene_data))

    print(f"Scene {scene_id} generated successfully.")
