# core/service/process/production/_legacy_project.py
"""
現行の制作の流れ(main.py)が使うProject(旧core/model/project.py)。ディレクトリの読み込みと生成器の保持を行う。
Projectの作り直し(docs/future_design.md)で削除する。
"""

import os
import yaml

from typing import Optional, List, Dict, Any

from core.schema.formats._legacy_drama import Actor, Scene, Transcript, GeminiVoice
from core.genai import SpeechGenerator, TextGenerator

class Project:
    def __init__(self, 
                 root_dir: str, 
                 tts_gen: Optional[SpeechGenerator] = None,
                 llm_gen: Optional[TextGenerator] = None,
                 system_instruction: Optional[str] = None,
                 ):
        self.root_dir = root_dir
        if not os.path.exists(root_dir):
            os.makedirs(root_dir)
            print(f"Created root directory: {root_dir}")
        
        self.project_dir = os.path.join(root_dir, "project")
        if not os.path.exists(self.project_dir):
            self.create_project()
        else:
            print(f"Project directory already exists: {self.project_dir}")

        self.working_dirs = []
        self.working_dirs.append(("sound_path", os.path.join(self.project_dir, "sound")))
        self.working_dirs.append(("script_path", os.path.join(self.project_dir, "script")))
        self.working_dirs.append(("actor_path", os.path.join(self.project_dir, "actor")))
        self.working_dirs.append(("plot_path", os.path.join(self.project_dir, "plot")))
        self.working_dirs.append(("scene_path", os.path.join(self.project_dir, "scene")))
        self.working_dirs.append(("dialog_path", os.path.join(self.project_dir, "dialog")))
        self.working_dirs.append(("character_path", os.path.join(self.project_dir, "character")))

        self.check_directories()

        # GUI等から直接オブジェクトが渡された場合も考慮しつつ初期化
        # get_actorsが呼ばれた後は character_name をキーとした辞書に更新される仕様
        self.actors = {}
        self.open_actors_yaml()
        
        self.acts = {}
        self.open_scenes_yaml()
        
        self.tts_gen = tts_gen
        self.llm_gen = llm_gen
        self.system_instruction = system_instruction
        
    def create_project(self):
        os.makedirs(self.project_dir, exist_ok=True)
        print(f"Created project directory: {self.project_dir}")
    
    def check_directories(self):
        for name, path in self.working_dirs:
            if not os.path.exists(path):
                os.makedirs(path)
                print(f"Created {name} at: {path}")
            else:
                print(f"{name} already exists at: {path}")

    def get_working_path(self, key: str) -> str:
        """working_dirsのタプルリストから特定のキーに対応するパスを返します"""
        for name, path in self.working_dirs:
            if name == key:
                return path
        return None
    
    def get_character_map(self) -> List[List[str]]:
        character_map = []
        for actor in self.actors.values():
            character_map.append([actor.label, actor.character_name])
        return character_map
    
    def open_actors_yaml(self):
        actor_path = self.get_working_path("actor_path")

        actor_files = sorted([f for f in os.listdir(actor_path) if f.endswith(('.yaml', '.yml'))])

        if not actor_files:
            print(f"Error: No YAML files found in actor_path: {actor_path}")
            return
        
        # アクター定義のロード
        for file_name in actor_files:
            actors_file = os.path.join(actor_path, file_name)
            try:
                if not os.path.exists(actors_file):
                    raise FileNotFoundError(f"[エラー] アクターYAMLファイルが見つかりません: {actors_file}")

                with open(actors_file, "r", encoding="utf-8") as f:
                    actors_data = yaml.safe_load(f)
                
                if not actors_data or not isinstance(actors_data, list):
                    raise ValueError(f"[エラー] {actors_file} のフォーマットが不正です。リスト形式で定義してください。")
                    
                self._load_actors_yaml(actors_data)
                
                print(f"Successfully loaded {len(self.actors)} actors from {actors_file}")
            except Exception as e:
                print(f"Failed to load actors from {file_name}: {e}")
                return


    def open_scenes_yaml(self):
        scene_path = self.get_working_path("scene_path")

        scene_files = sorted([f for f in os.listdir(scene_path) if f.endswith(('.yaml', '.yml'))])

        if not scene_files:
            print(f"Error: No YAML files found in scene_path: {scene_path}")
            return

        # シーン（幕）定義のロード
        for order, file_name in enumerate(scene_files):
            scene_file = os.path.join(scene_path, file_name)
            try:
                if not os.path.exists(scene_file):
                    raise FileNotFoundError(f"[エラー] シーンYAMLファイルが見つかりません: {scene_file}")

                with open(scene_file, "r", encoding="utf-8") as f:
                    scene_data = yaml.safe_load(f)
                
                if not scene_data or not isinstance(scene_data, dict):
                    raise ValueError(f"[エラー] {scene_file} のフォーマットが不正です。辞書(Map)形式で定義してください。")

                self.load_scenes_yaml(scene_data)
                
            except Exception as e:
                print(f"Failed to load scene from {file_name}: {e}")
                return
        
    def _load_actors_yaml(self, actors_data: Any) -> Dict[str, Actor]:
        for a_data in actors_data:
            # voiceが文字列で指定されている場合、GeminiVoice Enumに変換
            voice_str = a_data.get("voice")
            if isinstance(voice_str, str):
                try:
                    a_data["voice"] = GeminiVoice[voice_str]
                except KeyError:
                    print(f"Warning: ボイス '{voice_str}' は GeminiVoice に存在しません。デフォルトで ZEPHYR を割り当てます。")
                    a_data["voice"] = GeminiVoice.ZEPHYR

            # Actor インスタンスを生成
            actor = Actor(**a_data)

            self.actors[actor.character_name] = actor
        
        return self.actors

    def load_scenes_yaml(self, scene_data: Any) -> Scene:
        scripts = []     
        # 各プロンプト（セリフ）のパース処理
        for p_data in scene_data.get("transcripts", []):
            actor_name = p_data.pop("actor_name", None)
            if not actor_name:
                raise ValueError(f"[エラー] プロンプトデータに 'actor_name' が定義されていません: {p_data}")

            # 登録済みのアクターと紐付ける
            matched_actor = self.actors.get(actor_name)

            if not matched_actor:
                raise ValueError(
                    f"[整合性エラー] 原稿に登場するアクター '{actor_name}' は "
                    f"ロードされたアクターマップに存在しません。アクター定義を確認してください。"
                )

            # Transcriptを生成してシーンに追加
            scripts.append(
                Transcript(
                    actor=matched_actor,
                    **p_data
                )
            )

        scene = Scene(
            scene_id=scene_data["scene_id"],
            title=scene_data["title"],
            transcript=scripts
        )

        # 構築したシーンを管理リストへ登録
        self.acts[scene.scene_id] = scene
        
        print(f"Successfully loaded Scene [{scene.scene_id}]: '{scene.title}' with {len(scene.transcript)} transcripts")
        return scene