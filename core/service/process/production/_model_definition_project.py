# core/service/process/production/_model_definition_project.py
"""
モデル定義YAML(core.schema.formats.dramaturgy_definition)から、現行の制作の流れ(main.py)を動かすための仲介(暫定)。
現行の工程(dialogue_generator・scene_generator・sound_generator)と、その検査が使う_legacy_project.Projectと同じ
入口(get_working_path・get_character_map・load_scenes_yaml・actors・acts・生成器)を、モデルから用意する。
制作の流れを新しいモデルへ移すとき(docs/open_tasks.md)に、この仲介ごと置き換える。

ディレクトリの構成:
    <root_dir>/model/        モデル定義YAML(分割方式。apps/sample_dataの複製)。台詞はここのscripts/に書き戻す
    <root_dir>/work/script/  台詞の生成の出力(生成AIの応答そのまま。script_nnn.txt)
    <root_dir>/work/scene/   演出付きの原稿(旧来の形。scene_nnn.yaml)。Dialogueにcontextの置き場所が無いので、YAMLには書き戻さない
    <root_dir>/sound/        音声(scene_nnn.mp3)

話者の名前はCharacter.name(フルネーム)。Characterに呼び名の属性が無いため(docs/model_design.md「サンプルデータ」)。
"""

import os
import re
from pathlib import Path
from typing import Any, Optional

import yaml

from core.genai import SpeechGenerator, TextGenerator
from core.infra.io.model_definition_reader import build_dramaturgy_from_spec, read_spec
from core.infra.io.model_definition_writer import SCRIPT_DIR, scene_filename
from core.model.drama import Cast, Character, Dramaturgy, Scene
from core.prompt.drama_production import character_profile
from core.schema.formats._legacy_drama import Actor, GeminiVoice, Transcript
from core.schema.formats._legacy_drama import Scene as LegacyScene

MODEL_DIR = "model"


def _bare(name: object) -> str:
    """名前の照合用に空白を除く(生成AIは「加藤 喜一」を「加藤喜一」と書くことがある)。"""
    return re.sub(r"\s", "", str(name))


def is_model_definition_project(root_dir: str) -> bool:
    """root_dirが、モデル定義YAMLで作ったプロジェクト(<root_dir>/model/)か。"""
    return os.path.isdir(os.path.join(root_dir, MODEL_DIR))


class SceneUnit:
    """1つのシーン(プロット)と、そこから作る台詞・原稿・音声。keyはモデル定義YAMLでの幕・シーンのkey(書き戻しに使う)。"""

    def __init__(
        self,
        act_index: int,
        scene_index: int,
        act_key: str,
        scene_key: str,
        scene: Scene,
        number: int,
    ):
        self.act_index: int = act_index
        self.scene_index: int = scene_index
        self.act_key: str = act_key
        self.scene_key: str = scene_key
        self.scene: Scene = scene
        # 旧来の作業ファイルの名前(script_nnn.txt・scene_nnn.yaml・scene_nnn.mp3)の番号。全シーンでの通し番号
        self.number: int = number


class ModelDefinitionProject:
    """モデル定義YAMLから、現行の工程が使うProjectと同じ入口を用意する。"""

    def __init__(
        self,
        root_dir: str,
        tts_gen: Optional[SpeechGenerator] = None,
        llm_gen: Optional[TextGenerator] = None,
        system_instruction: Optional[str] = None,
    ):
        self.root_dir: str = root_dir
        self.model_dir: str = os.path.join(root_dir, MODEL_DIR)
        self.working_dirs: dict[str, str] = {
            "script_path": os.path.join(root_dir, "work", "script"),
            "scene_path": os.path.join(root_dir, "work", "scene"),
            "sound_path": os.path.join(root_dir, "sound"),
        }
        for path in self.working_dirs.values():
            os.makedirs(path, exist_ok=True)
        self.tts_gen: Optional[SpeechGenerator] = tts_gen
        self.llm_gen: Optional[TextGenerator] = llm_gen
        self.system_instruction: Optional[str] = system_instruction
        self.acts: dict[str, LegacyScene] = {}
        self.reload()

    def reload(self) -> None:
        """モデル定義YAMLを読み直す(台詞を書き戻した後など)。"""
        self.spec: dict[str, Any] = read_spec(self.model_dir)
        self.dramaturgy: Dramaturgy = build_dramaturgy_from_spec(self.spec)
        # 話者(配役のある人物)。名前→配役
        self.casts: dict[str, Cast] = {cast.character.name: cast for cast in self.dramaturgy.casts}
        self.actors: dict[str, Actor] = {name: _actor(cast) for name, cast in self.casts.items()}

    def get_working_path(self, key: str) -> Optional[str]:
        return self.working_dirs.get(key)

    def get_character_map(self) -> list[list[str]]:
        """原稿の工程に渡す、台詞の話者名→原稿のactor_nameの対応。どちらもCharacter.name。"""
        return [[name, name] for name in self.actors]

    def speakers(self) -> list[Character]:
        """台詞の話者(配役のある人物)。"""
        return [cast.character for cast in self.dramaturgy.casts]

    def dialogue_profiles(self) -> list[list[str]]:
        """台詞の工程に渡す人物設定([名前, 文章])。話者の人物だけ(話者でない人物は、人物関係の中に出てくる)。"""
        return [[character.name, character_profile(character)] for character in self.speakers()]

    def units(self) -> list[SceneUnit]:
        """全シーン(幕・シーンの順)。keyは重ね合わせた後の定義(spec)から取る(モデルはkeyを持たない)。"""
        units = []
        act_specs = self.spec["dramaturgy"].get("acts", [])
        for act_index, (act, act_spec) in enumerate(
            zip(self.dramaturgy.acts, act_specs, strict=True)
        ):
            for scene_index, (scene, scene_spec) in enumerate(
                zip(act.scenes, act_spec.get("scenes", []), strict=True)
            ):
                units.append(
                    SceneUnit(
                        act_index,
                        scene_index,
                        act_spec.get("key") or act.id,
                        scene_spec.get("key") or scene.id,
                        scene,
                        len(units),
                    )
                )
        return units

    def record_script(self, unit: SceneUnit, lines: list[tuple[str, str]]) -> Path:
        """
        台詞([(話者名, 台詞)])を、モデル定義YAMLのscripts/(このシーンのファイル)に書き戻し、読み直して形と参照を確かめる。
        話者は配役のkey(無ければid)で参照する。
        """
        cast_keys = {
            spec_cast["character"]: spec_cast.get("key") or spec_cast.get("id")
            for spec_cast in self.spec["dramaturgy"].get("casts", [])
        }
        character_keys = {
            _bare(spec_char["name"]): spec_char.get("key") or spec_char.get("id")
            for spec_char in self.spec["dramaturgy"].get("characters", [])
        }
        script_lines = []
        for order, (speaker, text) in enumerate(lines):
            cast_key = cast_keys.get(character_keys.get(_bare(speaker)))
            if cast_key is None:
                raise ValueError(f"話者 '{speaker}' の配役がありません")
            script_lines.append(
                {
                    "key": f"{unit.scene_key}_line_{order:03d}",
                    "order": order,
                    "cast": cast_key,
                    "text": text,
                }
            )
        document = {
            "dramaturgy": {
                "acts": [
                    {
                        "key": unit.act_key,
                        "scenes": [{"key": unit.scene_key, "script": {"lines": script_lines}}],
                    }
                ]
            }
        }
        path = Path(self.model_dir) / scene_filename(unit.act_index, unit.scene_index, SCRIPT_DIR)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"# {unit.scene_key}の台詞(制作の流れの台詞の工程で生成)\n"
            + yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        self.reload()
        return path

    def load_scenes_yaml(self, scene_data: dict[str, Any]) -> LegacyScene:
        """旧来の原稿(scene/*.yaml)を、音声の工程が使うSceneにする(_legacy_project.Project.load_scenes_yamlと同じ)。"""
        transcripts = []
        for item in scene_data.get("transcripts", []):
            actor_name = item.pop("actor_name", None)
            actor = next(
                (a for name, a in self.actors.items() if _bare(name) == _bare(actor_name)), None
            )
            if actor is None:
                raise ValueError(f"原稿の話者 '{actor_name}' に配役がありません")
            transcripts.append(Transcript(actor=actor, **item))
        scene = LegacyScene(
            scene_id=scene_data["scene_id"], title=scene_data["title"], transcript=transcripts
        )
        self.acts[scene.scene_id] = scene
        return scene


def _actor(cast: Cast) -> Actor:
    """配役を、音声の工程が使う旧来のActorにする。personality_*はCastに置き場所が無いので空(音声合成への指示では省かれる)。"""
    character = cast.character
    return Actor(
        character_name=character.name,
        voice=next(voice for voice in GeminiVoice if voice.voice_name == cast.voice_name),
        label=character.name,
        gender=character.gender or "",
        personality_title="",
        accent=cast.accent or "General English",
    )
