"""
制作の流れ(あらすじ → 台詞 → 原稿 → 音声)をローカルで実行する。
各工程の直後に、出力が次の工程に引き継げるかを検査し、合格すれば次の工程に進み、不合格ならそこで止める。

使い方(リポジトリ直下で。ROOT_DIRは<ROOT_DIR>/project/(旧来のテキストのファイル)か、
<ROOT_DIR>/model/(モデル定義YAML。apps/sample_dataの複製)を持つディレクトリ):
    .venv/bin/python main.py Project/TEST_PROJECT_01                     # 全あらすじを台詞から音声まで通す
    .venv/bin/python main.py Project/TEST_PROJECT_01 scene               # 既存の台詞を使い、原稿から音声まで通す
    .venv/bin/python main.py Project/TEST_PROJECT_01 --plot plot_001.txt # 1つのあらすじだけ
    .venv/bin/python main.py Project/TEST_PROJECT_01 check-scene         # 生成せず検査だけ
    .venv/bin/python main.py Project/TEST_PROJECT_02 --plot plot_001     # モデル定義YAMLのシーン(key)を1つだけ
開始する工程: dialogue(既定) / scene / sound。検査のみ: check-dialogue / check-scene / check-sound

plot/のあらすじを名前順に並べ、n番目(0から)を script/script_nnn.txt・scene/scene_nnn.yaml・
sound/scene_nnn.mp3 に対応させる。APIキーは ~/.aidc/secrets.env の AIDC_GEMINI_API_KEY を使う。
モデル定義YAMLのときは、シーン(幕・シーンの順)を同じ番号で対応させ、台詞をmodel/scripts/に書き戻す
(core/service/process/production/_model_definition_project.py)。
"""

import argparse
import copy
import os
import re
import sys
from dataclasses import dataclass
from typing import Optional

import yaml

from core.schema.formats._legacy_drama import AudioTag
from core.service.process.production._legacy_project import Project
from core.service.process.production._model_definition_project import (
    ModelDefinitionProject,
    SceneUnit,
    is_model_definition_project,
)
from core.prompt.drama_production import generate_sound_drama_prompt

LINE_RE = re.compile(r"^(?P<speaker>[^：:]{1,20})[：:](?P<text>.+)$")


def bare(name) -> str:
    """名前の照合用に空白を除く(生成AIは「加藤 喜一」を「加藤喜一」と書くことがある)。"""
    return re.sub(r"\s", "", str(name))


class HandoffError(Exception):
    pass


@dataclass
class Unit:
    """1つのあらすじと、そこから作る台詞・原稿・音声。"""

    plot_file: str
    script_file: str
    scene_id: str
    source: Optional[SceneUnit] = None  # モデル定義YAMLのシーン(旧来のテキストのファイルのときはNone)


def open_project(root_dir: str, with_generators: bool):
    if is_model_definition_project(root_dir):
        project = ModelDefinitionProject(root_dir=root_dir)
    else:
        project = Project(root_dir=root_dir)
    if not with_generators:
        return project
    from core.genai import (
        SpeechConfig,
        TextConfig,
        ThinkingLevel,
        create_speech_generator,
        create_text_generator,
    )
    from core.project.project import LlmSetting, TtsSetting
    from core.service.process.genai.generator_builder import saved_api_key

    # 生成AIの接続先。APIキーは~/.aidc/secrets.envに保存したもの(AIDC_GEMINI_API_KEY)を使う
    llm_setting = LlmSetting(client="Gemini", model="gemini-3.5-flash")
    tts_setting = TtsSetting(client="Gemini", model="gemini-3.1-flash-tts-preview")
    try:
        llm_key, tts_key = saved_api_key(llm_setting), saved_api_key(tts_setting)
    except ValueError as e:
        raise SystemExit(str(e)) from None

    project.system_instruction = "あなたは優秀な音声ドラマの演出家です。簡潔に回答してください。"
    llm_config = TextConfig(thinking_level=ThinkingLevel.MEDIUM, temperature=0.7, top_k=50, use_url_context=True)
    project.llm_gen = create_text_generator(llm_setting.client, llm_setting.model, api_key=llm_key, config=llm_config)
    project.tts_gen = create_speech_generator(
        tts_setting.client, tts_setting.model, api_key=tts_key, config=SpeechConfig(temperature=1.0)
    )
    return project


def list_units(project) -> list[Unit]:
    if isinstance(project, ModelDefinitionProject):
        return [Unit(u.scene_key, f"script_{u.number:03}.txt", f"scene_{u.number:03}", u) for u in project.units()]
    plot_dir = project.get_working_path("plot_path")
    plots = sorted(f for f in os.listdir(plot_dir) if f.endswith(".txt"))
    return [Unit(plot, f"script_{i:03}.txt", f"scene_{i:03}") for i, plot in enumerate(plots)]


def path(project: Project, key: str, name: str) -> str:
    return os.path.join(project.get_working_path(key), name)


def report(title: str, errors: list[str], warnings: list[str], info: list[str]):
    print(f"\n===== 検査: {title} =====")
    for m in info:
        print(f"  [情報] {m}")
    for m in warnings:
        print(f"  [警告] {m}")
    for m in errors:
        print(f"  [不合格] {m}")
    if errors:
        raise HandoffError(f"{title}: 次の工程に引き継げません")
    print("  → 合格(次の工程に引き継げる)")


# ---------- 工程1: 台詞 ----------

def step_dialogue(project: Project, unit: Unit):
    from core.service.process.production import generate_dialogue

    if unit.source is not None:  # モデル定義YAML: 話者の人物設定をCharacterから組み立てる
        profiles = project.dialogue_profiles()
        synopsis = unit.source.scene.synopsis
    else:
        profiles = []
        char_dir = project.get_working_path("character_path")
        for name in sorted(os.listdir(char_dir)):
            with open(os.path.join(char_dir, name), encoding="utf-8") as f:
                profiles.append([os.path.splitext(name)[0], f.read()])
        with open(path(project, "plot_path", unit.plot_file), encoding="utf-8") as f:
            synopsis = f.read()
    generate_dialogue(project=project, synopsis=synopsis, profiles=profiles,
                      output_file=path(project, "script_path", unit.script_file), num_char=len(synopsis) * 2)


def parse_dialogue(project: Project, unit: Unit) -> tuple[list[tuple[str, str]], str]:
    with open(path(project, "script_path", unit.script_file), encoding="utf-8") as f:
        text = f.read()
    return [(m["speaker"].strip(), m["text"].strip()) for line in text.splitlines()
            if line.strip() and (m := LINE_RE.match(line.strip()))], text


def check_dialogue(project: Project, unit: Unit):
    errors, warnings, info = [], [], []
    title = f"台詞 → 原稿({unit.script_file})"
    p = path(project, "script_path", unit.script_file)
    if not os.path.exists(p):
        report(title, [f"{p} がありません"], [], [])
    lines, text = parse_dialogue(project, unit)
    nonblank = [ln.strip() for ln in text.splitlines() if ln.strip()]
    labels = {bare(a.label) for a in project.actors.values()}
    names = {bare(a.character_name) for a in project.actors.values()}

    info.append(f"台詞 {len(lines)} 行 / 空行以外 {len(nonblank)} 行、本文 {sum(len(t) for _, t in lines)} 文字")
    if not lines:
        errors.append("「人物名：台詞」の形式の行がありません")
    bad = [ln for ln in nonblank if not LINE_RE.match(ln)]
    if bad:
        errors.append(f"形式に合わない行 {len(bad)} 件(冒頭の解説など): {bad[:3]}")
    speakers = {bare(s) for s, _ in lines}
    info.append(f"話者: {sorted(speakers)}(原稿の工程の対応表のラベル: {sorted(labels)})")
    # 原稿の工程は「ラベル(喜一)→ actor_name(Kiichi)」の対応表を渡す。対応表に無い名前は対応付けを生成AI任せにすることになる
    unknown = speakers - labels
    if unknown - names:
        errors.append(f"actors.yaml に無い話者: {sorted(unknown - names)}")
    elif unknown:
        warnings.append(f"ラベルではなく character_name で書かれた話者: {sorted(unknown)}(対応表に無いので生成AIの推測に依存)")
    stage = [t for _, t in lines if re.search(r"[（(].+?[)）]", t)]
    if stage:
        warnings.append(f"カッコ書き(ト書きの疑い) {len(stage)} 件: {stage[:2]}")
    # モデル定義YAMLのときは、台詞をmodel/scripts/に書き戻し、読み直せるか(形・話者の配役の参照)を確かめる
    if unit.source is not None and not errors:
        try:
            written = project.record_script(unit.source, lines)
            scene = next(u.scene for u in project.units() if u.scene_key == unit.source.scene_key)
            info.append(f"台詞 {len(scene.script.lines)} 行を {written} に書き戻し、読み直せた")
        except Exception as e:  # noqa: BLE001
            errors.append(f"台詞のモデル定義YAMLへの書き戻しに失敗: {type(e).__name__}: {e}")
    report(title, errors, warnings, info)


# ---------- 工程2: 原稿 ----------

def step_scene(project: Project, unit: Unit):
    from core.service.process.production import generate_scene

    with open(path(project, "script_path", unit.script_file), encoding="utf-8") as f:
        dialog = f.read()
    try:
        generate_scene(project=project, scene_id=unit.scene_id, dialog=dialog,
                       output_file=path(project, "scene_path", unit.scene_id + ".yaml"))
    except Exception as e:  # noqa: BLE001
        raise HandoffError(f"原稿の生成・読み込みに失敗: {type(e).__name__}: {e}") from e


def check_scene(project: Project, unit: Unit):
    errors, warnings, info = [], [], []
    title = f"原稿 → 音声({unit.scene_id}.yaml)"
    p = path(project, "scene_path", unit.scene_id + ".yaml")
    if not os.path.exists(p):
        report(title, [f"{p} がありません"], [], [])
    with open(p, encoding="utf-8") as f:
        raw = f.read()
    if "```" in raw:
        errors.append("コードブロックの記号(```)が残っている")
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        report(title, [f"YAMLとして読めない: {e}"], [], [])
    if not isinstance(data, dict):
        report(title, [f"最上位が辞書ではない: {type(data).__name__}"], [], [])

    for key in ("scene_id", "title", "transcripts"):
        if key not in data:
            errors.append(f"キー {key} が無い")
    if data.get("scene_id") != unit.scene_id:
        errors.append(f"scene_id が {data.get('scene_id')!r}({unit.scene_id!r} のはず)")
    items = data.get("transcripts") or []
    info.append(f"title: {data.get('title')!r}、台詞 {len(items)} 件")

    for i, t in enumerate(items, 1):
        missing = [k for k in ("actor_name", "context", "scene", "directors_note", "text", "order") if k not in t]
        if missing:
            errors.append(f"{i}件目: {missing} が無い")
        dn = t.get("directors_note") or {}
        if not isinstance(dn, dict) or not {"style", "pace"} <= set(dn):
            errors.append(f"{i}件目: directors_note に style/pace が無い")
        if bare(t.get("actor_name")) not in {bare(name) for name in project.actors}:
            errors.append(f"{i}件目: actor_name {t.get('actor_name')!r} が actors.yaml に無い")
    # 出力例の記入欄(<…>)が埋まらずに残っていないか
    for i, t in enumerate(items, 1):
        dn = t.get("directors_note") if isinstance(t.get("directors_note"), dict) else {}
        values = [data.get("title"), t.get("actor_name"), t.get("context"), t.get("scene"), t.get("text"), *dn.values()]
        left = [v for v in values if isinstance(v, str) and re.fullmatch(r"\s*<.*>\s*", v)]
        if left:
            errors.append(f"{i}件目: 記入欄が残っている: {left}")
    orders = [t.get("order") for t in items]
    if orders != list(range(1, len(items) + 1)):
        warnings.append(f"order が1からの連番でない: {orders}")

    # 台詞の工程の出力との対応(行数・話者の並び)
    if os.path.exists(path(project, "script_path", unit.script_file)):
        lines, _ = parse_dialogue(project, unit)
        label_to_name = {bare(a.label): bare(a.character_name) for a in project.actors.values()}
        expected = [label_to_name.get(bare(s), bare(s)) for s, _ in lines]
        actual = [bare(t.get("actor_name")) for t in items]
        if len(expected) != len(actual):
            warnings.append(f"台詞の行数 {len(expected)} と原稿の件数 {len(actual)} が違う")
        elif expected != actual:
            diff = [i + 1 for i, (e, a) in enumerate(zip(expected, actual, strict=True)) if e != a]
            warnings.append(f"話者の並びが台詞と違う位置: {diff}")
        else:
            info.append("台詞の行数・話者の並びが一致")

    tags = AudioTag.get_all_values()
    unknown_tags = {tag for t in items for tag in re.findall(r"\[.*?\]", str(t.get("text", ""))) if tag not in tags}
    if unknown_tags:
        warnings.append(f"推奨外の感情タグ: {sorted(unknown_tags)}")

    # 実際に音声の工程が使う形(Scene・音声合成への指示)に組み立てられるか
    if not errors:
        try:
            scene = project.load_scenes_yaml(copy.deepcopy(data))
            for tr in sorted(scene.transcript, key=lambda x: x.order):
                generate_sound_drama_prompt(tr)
                _ = tr.actor.voice_name
            info.append(f"Scene に組み立て、{len(scene.transcript)} 件の音声合成の指示を作成できた")
        except Exception as e:  # noqa: BLE001
            errors.append(f"Scene・指示の組み立てに失敗: {type(e).__name__}: {e}")
    report(title, errors, warnings, info)


# ---------- 工程3: 音声 ----------

def step_sound(project: Project, unit: Unit):
    from core.service.process.production import generate_sound_drama

    # 原稿はファイル経由で引き継ぐ(scene/ のファイルから読み込み直す)
    with open(path(project, "scene_path", unit.scene_id + ".yaml"), encoding="utf-8") as f:
        scene = project.load_scenes_yaml(yaml.safe_load(f))
    generate_sound_drama(project, scene)


def check_sound(project: Project, unit: Unit):
    from pydub import AudioSegment

    errors, warnings, info = [], [], []
    title = f"音声({unit.scene_id}.mp3)"
    p = path(project, "sound_path", unit.scene_id + ".mp3")
    if not os.path.exists(p):
        report(title, [f"{p} がありません"], [], [])
    audio = AudioSegment.from_mp3(p)
    sec = len(audio) / 1000
    info.append(f"{p}: {sec:.1f} 秒、{os.path.getsize(p) // 1024} KB、{audio.channels}ch {audio.frame_rate}Hz")
    n = len(project.acts[unit.scene_id].transcript) if unit.scene_id in project.acts else 0
    if sec <= 0:
        errors.append("長さが0")
    elif n and sec / n < 1.0:
        warnings.append(f"台詞1件あたり {sec / n:.2f} 秒と短い(合成に失敗した台詞がある疑い)")
    if audio.dBFS == float("-inf"):
        errors.append("無音")
    report(title, errors, warnings, info)


# 工程の順番。各工程の直後に検査し、合格した場合だけ次の工程に進む
PIPELINE = [
    ("dialogue", step_dialogue, check_dialogue),
    ("scene", step_scene, check_scene),
    ("sound", step_sound, check_sound),
]
CHECKS = {f"check-{name}": check for name, _, check in PIPELINE}


def main():
    names = [name for name, _, _ in PIPELINE]
    parser = argparse.ArgumentParser(description="制作の流れ(あらすじ → 台詞 → 原稿 → 音声)を実行する")
    parser.add_argument(
        "root_dir", help="<root_dir>/project/ か <root_dir>/model/ を持つディレクトリ(例: Project/TEST_PROJECT_01)"
    )
    parser.add_argument("start", nargs="?", default="dialogue", choices=names + list(CHECKS),
                        help="開始する工程(既定: dialogue)、または検査のみ")
    parser.add_argument(
        "--plot", help="このあらすじ(plot/のファイル名。モデル定義YAMLのときはシーンのkey)だけを処理する"
    )
    args = parser.parse_args()

    for sample in ("apps/sample_project", "apps/sample_data"):
        if os.path.realpath(args.root_dir).startswith(os.path.realpath(sample)):
            raise SystemExit(f"{sample}/ は読み取り専用です。Project/TEST_PROJECT_## に複製して使ってください。")
    if not (os.path.isdir(os.path.join(args.root_dir, "project")) or is_model_definition_project(args.root_dir)):
        raise SystemExit(f"{args.root_dir}/project/ も {args.root_dir}/model/ もありません")

    project = open_project(args.root_dir, with_generators=args.start not in CHECKS)
    units = list_units(project)
    if args.plot:
        units = [u for u in units if u.plot_file == args.plot]
        if not units:
            raise SystemExit(f"あらすじ {args.plot} がありません")

    try:
        for unit in units:
            print(f"\n########## {unit.plot_file} → {unit.script_file} → {unit.scene_id} ##########")
            if args.start in CHECKS:
                CHECKS[args.start](project, unit)
                continue
            for name, step, check in PIPELINE[names.index(args.start):]:
                print(f"\n##### 工程: {name} #####")
                step(project, unit)
                check(project, unit)
        if args.start not in CHECKS:
            print(f"\n完走: {len(units)} 場面の音声ファイルまで作成できた")
    except HandoffError as e:
        print(f"\n中断: {e}")
        sys.exit(1)


# --- Execution Block ---
if __name__ == "__main__":
    main()
