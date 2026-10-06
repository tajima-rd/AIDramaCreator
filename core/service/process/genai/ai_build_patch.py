# core/service/process/genai/ai_build_patch.py
"""
Build with AIの生成AIの提案を、編集用の下書きへ重ねる部分YAML(docs/database_design.md「部分YAMLの重ね合わせ」)にする。
工程ごとの規則は docs/architecture.md 10節。

- 企画書(Proposal): 対話は変わった項目だけ(空で返した項目は変えない)、ワンショットは丸ごと置き換え(空の項目は消す)
- 人物・まとまり・人物関係(Characters・Groups・Relationships): 追加と更新だけで、削除はしない。既存の要素は名前で対応付ける
  (人物=名前、まとまり=名前、人物関係=起点・相手の人物と関係の名前)。空の値では既存の値を消さない。名前の分からない人物を
  指すメンバー・関係は外して、注意として返す。Charactersの工程で出てきた人物と、新しく作った人物関係は、作品の参照にも加える
- 配役(Casting): 追加と更新だけ。配役は人物の名前で対応付ける(作品の配役のうち、その人物のもの)。空の値では既存の値を消さない。
  いない人物の配役・決まりに無い値(役の重さ・声の性別)は外して注意を返す。配役した人物は作品の登場人物の参照にも加える
- 声(Audition): 配役ごとに演者(Actor)の話者・音声合成の提供元・モデルを決める。演者がいなければ作る。声の一覧に無い声・
  配役の無い人物は外して注意を返す
- あらすじ(Synopsis): 作品全体のあらすじと、今ある幕の題・あらすじの更新だけ(幕は番号で指し、追加・削除しない)。
  空の値では既存の値を消さない。無い番号の幕は外して注意を返す
- シーンのあらすじ(Scenes): 今あるシーンの題・あらすじの更新だけ(シーンは幕とシーンの番号で指し、追加・削除しない)。
  場所・時期・状況は変えない。空の値では既存の値を消さない。無い番号のシーンは外して注意を返す
- 演出付きの原稿(Direction): 選んだシーンの台詞の1行ごとに、演出付きの台詞(Dialogue)を作るか書き換える(台詞と対応付け、識別子を保つ)。
  音声にする文は、感情タグを除くと台詞の文言と同じでなければならない(違えば台詞のまま使い、注意を返す)。一覧に無い感情タグは外す。
  訳文は、音声の言語が制作の言語と違う作品だけ。演出の無い台詞は、今の原稿を残す(無ければ台詞のままの原稿を作る)
- 台詞(Script): 選んだシーンの台詞の全体を置き換える(今の行を順に書き換え、余った行は消し、足りない行は足す)。話者は人物の名前で
  指し、作品の配役にいない人物の行・空の行は外して注意を返す
"""

from typing import Any, Optional

from core.genai import VoiceInfo
from core.model.drama import CastBilling, Dramaturgy, VoiceGender
from core.prompt.ai_build.casting import BILLING_LABELS, CastDraft, VoiceChoice
from core.prompt.ai_build.characters import CharacterDraft, GroupDraft, RelationshipDraft
from core.prompt.ai_build.common import BuildMode
from core.prompt.ai_build.proposal import ProposalReply
from core.prompt.ai_build.scene_synopsis import SceneSynopsisReply
from core.prompt.ai_build.direction import DialogueDirectionDraft, bare_text, remove_unknown_tags
from core.prompt.ai_build.script import LineDraft
from core.prompt.ai_build.synopsis import SynopsisReply, ordered_acts, ordered_scenes

# 提案の中で新しい要素を参照するためのkeyの接頭辞(下書きのkeyは種類と通し番号なので重ならない)
NEW_CHARACTER_KEY = "ai_character_"
NEW_GROUP_KEY = "ai_group_"
NEW_RELATIONSHIP_KEY = "ai_relationship_"
NEW_CAST_KEY = "ai_cast_"
NEW_ACTOR_KEY = "ai_actor_"


class PatchOutcome:
    """patchは部分YAMLの対応表(変わる所が無ければNone)、changesは利用者に見せる変更の一覧、warningsは提案から外したものの注意。
    shownは画面に出す提案(提案から外したものを除いたもの。Noneなら生成AIの応答のまま出す)。"""

    def __init__(
        self,
        patch: Optional[dict[str, Any]],
        changes: list[str],
        warnings: list[str],
        shown: Optional[dict[str, Any]] = None,
    ):
        self.patch: Optional[dict[str, Any]] = patch
        self.changes: list[str] = changes
        self.warnings: list[str] = warnings
        self.shown: Optional[dict[str, Any]] = shown


def _text(value: Optional[str]) -> Optional[str]:
    value = (value or "").strip()
    return value or None


def _compact(values: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in values.items() if v is not None}


# ---------------------------------------------------------------------------
# 企画書
# ---------------------------------------------------------------------------

_PROPOSAL_TEXT_FIELDS = ("title", "catchphrase", "logline", "intent", "target_area", "synopsis")


def proposal_patch(dramaturgy: Dramaturgy, reply: ProposalReply, mode: BuildMode) -> PatchOutcome:
    """企画書の提案を部分YAMLにする。changesは変わる項目の名前。"""
    if mode is BuildMode.DIALOGUE and not reply.has_proposal:
        return PatchOutcome(None, [], [])
    current = dramaturgy.proposal
    draft = reply.proposal
    values: dict[str, Any] = {}
    for field in _PROPOSAL_TEXT_FIELDS:
        new = _text(getattr(draft, field))
        if mode is BuildMode.DIALOGUE and new is None:
            continue  # 対話では、空で返した項目は変えない
        if new != getattr(current, field):
            values[field] = new
    new_characters = [
        _compact({"name": _text(c.name), "description": _text(c.description)})
        for c in draft.characters
        if _text(c.name) or _text(c.description)
    ]
    current_characters = [
        _compact({"name": c.name, "description": c.description}) for c in current.characters
    ]
    if (
        not (mode is BuildMode.DIALOGUE and not new_characters)
        and new_characters != current_characters
    ):
        values["characters"] = new_characters
    if not values:
        return PatchOutcome(None, [], [])
    return PatchOutcome(
        {"dramaturgies": [{"id": dramaturgy.id, "proposal": values}]}, list(values), []
    )


# ---------------------------------------------------------------------------
# あらすじ
# ---------------------------------------------------------------------------


def synopsis_patch(dramaturgy: Dramaturgy, reply: SynopsisReply) -> PatchOutcome:
    """作品と幕のあらすじの提案を部分YAMLにする(更新だけ。空の値は変えない)。changesは変わる項目の説明。"""
    values: dict[str, Any] = {}
    changes: list[str] = []
    warnings: list[str] = []
    synopsis = _text(reply.synopsis)
    if synopsis is not None and synopsis != dramaturgy.synopsis:
        values["synopsis"] = synopsis
        changes.append("作品全体のあらすじ")
    acts = ordered_acts(dramaturgy)
    act_values: dict[str, dict[str, Any]] = {}
    for draft in reply.acts:
        if not 1 <= draft.number <= len(acts):
            warnings.append(f"第{draft.number}幕はありません(幕は{len(acts)}つ)。幕は増やさないので、外しました。")
            continue
        act = acts[draft.number - 1]
        fields = act_values.setdefault(act.id, {})
        for field, label in (("title", "題"), ("synopsis", "あらすじ")):
            new = _text(getattr(draft, field))
            if new is not None and new != getattr(act, field):
                fields[field] = new
                change = f"第{draft.number}幕の{label}"
                if change not in changes:
                    changes.append(change)
    patch_acts = [{"id": act_id, **fields} for act_id, fields in act_values.items() if fields]
    if patch_acts:
        values["acts"] = patch_acts
    if not values:
        return PatchOutcome(None, [], warnings)
    return PatchOutcome({"dramaturgies": [{"id": dramaturgy.id, **values}]}, changes, warnings)


def scene_synopsis_patch(dramaturgy: Dramaturgy, reply: SceneSynopsisReply) -> PatchOutcome:
    """シーンの題・あらすじの提案を部分YAMLにする(更新だけ。空の値は変えない)。changesは変わる項目の説明。"""
    changes: list[str] = []
    warnings: list[str] = []
    acts = ordered_acts(dramaturgy)
    scene_values: dict[str, dict[str, dict[str, Any]]] = {}  # 幕のid → シーンのid → 変える値
    for draft in reply.scenes:
        if not 1 <= draft.act <= len(acts):
            warnings.append(f"第{draft.act}幕はありません(幕は{len(acts)}つ)。シーンは増やさないので、外しました。")
            continue
        act = acts[draft.act - 1]
        scenes = ordered_scenes(act)
        if not 1 <= draft.scene <= len(scenes):
            warnings.append(
                f"第{draft.act}幕のシーン{draft.scene}はありません(この幕のシーンは{len(scenes)}つ)。シーンは増やさないので、外しました。"
            )
            continue
        scene = scenes[draft.scene - 1]
        fields = scene_values.setdefault(act.id, {}).setdefault(scene.id, {})
        for field, label in (("title", "題"), ("synopsis", "あらすじ")):
            new = _text(getattr(draft, field))
            if new is not None and new != getattr(scene, field):
                fields[field] = new
                change = f"第{draft.act}幕のシーン{draft.scene}の{label}"
                if change not in changes:
                    changes.append(change)
    patch_acts = []
    for act_id, scenes in scene_values.items():
        patch_scenes = [{"id": scene_id, **fields} for scene_id, fields in scenes.items() if fields]
        if patch_scenes:
            patch_acts.append({"id": act_id, "scenes": patch_scenes})
    if not patch_acts:
        return PatchOutcome(None, [], warnings)
    return PatchOutcome({"dramaturgies": [{"id": dramaturgy.id, "acts": patch_acts}]}, changes, warnings)


# ---------------------------------------------------------------------------
# 演出付きの原稿
# ---------------------------------------------------------------------------

_DIRECTION_FIELDS = ("style", "pace", "dynamics", "emotion", "pause_after")


def _known_tags(text: str, where: str, warnings: list[str]) -> str:
    """一覧に無い感情タグを外す(外したら注意)。"""
    text, unknown = remove_unknown_tags(text)
    warnings += [f"{where}の感情タグ「{tag}」は使えないので、外しました。" for tag in unknown]
    return text


def direction_patch(
    content: dict[str, Any],
    dramaturgy_id: str,
    scene_id: str,
    drafts: list[DialogueDirectionDraft],
    translates: bool,
) -> PatchOutcome:
    """シーンの演出付きの原稿の提案を部分YAMLにする(台詞の1行ごとに、演出付きの台詞を作るか書き換える)。"""
    dramaturgy = _dramaturgy_spec(content, dramaturgy_id)
    act, scene = next(
        (a, sc) for a in dramaturgy.get("acts", []) for sc in a.get("scenes", []) if sc.get("id") == scene_id
    )
    lines = sorted((scene.get("script") or {}).get("lines") or [], key=lambda line: line.get("order", 0))
    existing = {
        e["line"]["ref"]: e for e in scene.get("elements") or [] if e.get("type") == "dialogue" and e.get("line")
    }
    warnings: list[str] = []
    by_number: dict[int, DialogueDirectionDraft] = {}
    for draft in drafts:
        if not 1 <= draft.number <= len(lines):
            warnings.append(f"台詞{draft.number}はありません(台詞は{len(lines)}行)。台詞は増やさないので、外しました。")
        elif draft.number in by_number:
            warnings.append(f"台詞{draft.number}の演出が2つあるので、後のものを外しました。")
        else:
            by_number[draft.number] = draft

    elements: list[dict[str, Any]] = []
    shown: list[dict[str, Any]] = []
    changed = 0
    for number, line in enumerate(lines, start=1):
        current = existing.get(line["key"])
        draft = by_number.get(number)
        if draft is None:
            if current is not None:
                continue  # 演出の無い台詞は、今の原稿を残す
            warnings.append(f"台詞{number}の演出が無いので、台詞のままの原稿にしました。")
            draft = DialogueDirectionDraft(
                number=number, text="", action="", style="", pace="", dynamics="", emotion="", pause_after="", translated_text=""
            )
        where = f"台詞{number}"
        text = _known_tags(draft.text or "", where, warnings)
        if bare_text(text) != bare_text(line["text"]):
            if _text(draft.text):
                warnings.append(f"{where}の音声にする文が台詞の文言と違うので、台詞のまま使いました(文言はScriptの工程で直す)。")
            text = line["text"]
        translated = _text(_known_tags(draft.translated_text or "", f"{where}の訳文", warnings)) if translates else None
        if translates and translated is None:
            warnings.append(f"{where}の訳文がありません。")
        values: dict[str, Any] = {
            "type": "dialogue",
            "order": line.get("order", number - 1),
            "line": {"ref": line["key"]},
            "cast": {"ref": line["cast"]["ref"]},
            "text": text,
            "action": _text(draft.action),
            "direction": {field: _text(getattr(draft, field)) for field in _DIRECTION_FIELDS},
            "translated_text": translated,
        }
        if current is not None:
            same = (
                current.get("text") == values["text"]
                and current.get("action") == values["action"]
                and _compact(current.get("direction") or {}) == _compact(values["direction"])
                and current.get("translated_text") == values["translated_text"]
            )
            if same:
                continue
            elements.append({"id": current["id"], **values})  # nullの値は、今の値を消す
        else:
            elements.append({**_compact(values), "direction": _compact(values["direction"])})
        changed += 1
        shown.append({"number": number, "speaker_text": line["text"], **_compact({**values, **values["direction"]})})
    if not elements:
        return PatchOutcome(None, [], warnings)
    for item in shown:
        for key in ("type", "order", "line", "cast", "direction"):
            item.pop(key, None)
    patch = {
        "dramaturgies": [
            {
                "id": dramaturgy_id,
                "acts": [{"id": act["id"], "scenes": [{"id": scene_id, "elements": elements}]}],
            }
        ]
    }
    created = sum(1 for e in elements if "id" not in e)
    change = f"{changed}行の台詞に演出を付ける" + (f"(新しく{created}行)" if created else "")
    return PatchOutcome(patch, [change], warnings, {"dialogues": shown})


# ---------------------------------------------------------------------------
# 台詞
# ---------------------------------------------------------------------------


def script_patch(
    content: dict[str, Any], dramaturgy_id: str, scene_id: str, drafts: list[LineDraft]
) -> PatchOutcome:
    """シーンの台詞の提案を部分YAMLにする(台詞の全体を置き換える)。changesは変わる内容の説明。"""
    dramaturgy = _dramaturgy_spec(content, dramaturgy_id)
    act, scene = next(
        (a, sc) for a in dramaturgy.get("acts", []) for sc in a.get("scenes", []) if sc.get("id") == scene_id
    )
    names = {c["key"]: c["name"].strip() for c in content.get("characters", []) if c.get("name")}
    cast_keys = {
        names[c["character"]["ref"]]: c["key"]
        for c in dramaturgy.get("casts", [])
        if c.get("character") and c["character"]["ref"] in names
    }
    warnings: list[str] = []
    new_lines: list[tuple[str, str]] = []  # (配役のkey, 台詞)
    shown: list[dict[str, str]] = []  # 画面に出す、反映する行
    for draft in drafts:
        speaker, text = draft.speaker.strip(), _text(draft.text)
        if text is None:
            continue
        if speaker not in cast_keys:
            warnings.append(f"「{speaker}」は配役にいないので、その台詞「{text[:20]}」を外しました。")
            continue
        new_lines.append((cast_keys[speaker], text))
        shown.append({"speaker": speaker, "text": text})
    current = sorted((scene.get("script") or {}).get("lines") or [], key=lambda line: line.get("order", 0))
    if not new_lines:
        if drafts:
            warnings.append("話せる人物の台詞が無いので、台詞は変えません。")
        return PatchOutcome(None, [], warnings)
    if [(line["cast"]["ref"], line["text"]) for line in current] == new_lines:
        return PatchOutcome(None, [], warnings)
    patch_lines: list[dict[str, Any]] = []
    for order, (cast_key, text) in enumerate(new_lines):
        line = {"order": order, "cast": {"ref": cast_key}, "text": text}
        patch_lines.append({"id": current[order]["id"], **line} if order < len(current) else line)
    patch_lines += [{"id": line["id"], "delete": True} for line in current[len(new_lines):]]
    patch = {
        "dramaturgies": [
            {
                "id": dramaturgy_id,
                "acts": [{"id": act["id"], "scenes": [{"id": scene_id, "script": {"lines": patch_lines}}]}],
            }
        ]
    }
    change = f"台詞を{len(new_lines)}行にする" + (f"(今は{len(current)}行)" if current else "")
    return PatchOutcome(patch, [change], warnings, {"lines": shown})


# ---------------------------------------------------------------------------
# 人物・まとまり・人物関係
# ---------------------------------------------------------------------------


def _character_fields(draft: CharacterDraft) -> dict[str, Any]:
    """人物の属性(空の値は書かない=既存の値を残す。特徴は返したときだけ一覧ごと置き換える)。"""
    fields: dict[str, Any] = _compact(
        {"reading": _text(draft.reading), "gender": _text(draft.gender), "age": _text(draft.age)}
    )
    speech = _compact(
        {
            "first_person": _text(draft.first_person),
            "tone": _text(draft.tone),
            "description": _text(draft.speech_description),
        }
    )
    if speech:
        fields["speech_style"] = speech
    characteristics = [
        {
            "item": c.item.strip(),
            **_compact({"definition": _text(c.definition), "description": _text(c.description)}),
            "features": [
                {
                    "item": f.item.strip(),
                    **_compact(
                        {
                            "value": _text(f.value),
                            "definition": _text(f.definition),
                            "description": _text(f.description),
                        }
                    ),
                }
                for f in c.features
                if f.item.strip()
            ],
        }
        for c in draft.characteristics
        if c.item.strip()
    ]
    if characteristics:
        fields["characteristics"] = characteristics
    return fields


class _World:
    """下書きの中身(id・key付きの対応表)から、名前で人物・まとまり・関係を引く。"""

    def __init__(self, content: dict[str, Any], dramaturgy_id: str):
        self.content = content
        self.dramaturgy = next(
            d for d in content.get("dramaturgies", []) if d.get("id") == dramaturgy_id
        )
        self.character_keys: dict[str, str] = {
            c["name"].strip(): c["key"] for c in content.get("characters", []) if c.get("name")
        }
        self.characters_by_name: dict[str, dict[str, Any]] = {
            c["name"].strip(): c for c in content.get("characters", []) if c.get("name")
        }
        self.groups_by_name: dict[str, dict[str, Any]] = {
            g["name"].strip(): g for g in content.get("character_groups", []) if g.get("name")
        }
        self.relationships = content.get("relationships", [])
        self.patch: dict[str, list[dict[str, Any]]] = {}
        self.changes: list[str] = []
        self.warnings: list[str] = []
        self.mentioned_characters: list[str] = []  # 作品の参照に加える人物のkey
        self.new_relationships: list[str] = []
        self._counter = 0

    def _new_key(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}{self._counter}"

    def add_characters(self, drafts: list[CharacterDraft]) -> None:
        for draft in drafts:
            name = (draft.name or "").strip()
            if not name:
                continue
            fields = _character_fields(draft)
            if name in self.characters_by_name:
                if fields:
                    self.patch.setdefault("characters", []).append(
                        {"id": self.characters_by_name[name]["id"], **fields}
                    )
                    self.changes.append(f"人物「{name}」を更新")
            elif name not in self.character_keys:
                key = self._new_key(NEW_CHARACTER_KEY)
                self.character_keys[name] = key
                self.patch.setdefault("characters", []).append({"key": key, "name": name, **fields})
                self.changes.append(f"人物「{name}」を追加")
            key = self.character_keys[name]
            if key not in self.mentioned_characters:
                self.mentioned_characters.append(key)

    def _member_refs(self, group_name: str, names: list[str]) -> list[dict[str, str]]:
        refs = []
        for name in (n.strip() for n in names):
            if not name:
                continue
            if name not in self.character_keys:
                self.warnings.append(
                    f"まとまり「{group_name}」のメンバー「{name}」は人物にいないので、外しました。"
                )
                continue
            ref = {"ref": self.character_keys[name]}
            if ref not in refs:
                refs.append(ref)
        return refs

    def add_groups(self, drafts: list[GroupDraft], keep_members: bool) -> None:
        """keep_membersなら、既存のまとまりのメンバーを残して足す(Charactersの工程の大まかな提案)。"""
        for draft in drafts:
            name = (draft.name or "").strip()
            if not name:
                continue
            members = self._member_refs(name, draft.members)
            fields = _compact({"kind": _text(draft.kind), "description": _text(draft.description)})
            existing = self.groups_by_name.get(name)
            if existing is not None:
                current = list(existing.get("members", []))
                merged = (
                    current + [m for m in members if m not in current] if keep_members else members
                )
                if members and merged != current:
                    fields["members"] = merged
                if fields:
                    self.patch.setdefault("character_groups", []).append(
                        {"id": existing["id"], **fields}
                    )
                    self.changes.append(f"まとまり「{name}」を更新")
            else:
                key = self._new_key(NEW_GROUP_KEY)
                self.groups_by_name[name] = {"key": key, "name": name, "members": members}
                self.patch.setdefault("character_groups", []).append(
                    {"key": key, "name": name, **fields, "members": members}
                )
                self.changes.append(f"まとまり「{name}」を追加")

    def add_relationships(self, drafts: list[RelationshipDraft]) -> None:
        for draft in drafts:
            source, target, label = (
                (draft.source or "").strip(),
                (draft.target or "").strip(),
                (draft.label or "").strip(),
            )
            title = f"{source}→{target}「{label}」"
            if not (source and target and label):
                continue
            missing = [n for n in (source, target) if n not in self.character_keys]
            if missing:
                self.warnings.append(
                    f"人物関係 {title}の人物「{'・'.join(missing)}」がいないので、外しました。"
                )
                continue
            if source == target:
                continue
            source_ref, target_ref = {"ref": self.character_keys[source]}, {
                "ref": self.character_keys[target]
            }
            fields = _compact(
                {
                    "description": _text(draft.description),
                    "form_of_address": _text(draft.form_of_address),
                    "tone": _text(draft.tone),
                }
            )
            existing = next(
                (
                    r
                    for r in self.relationships
                    if r.get("source") == source_ref
                    and r.get("target") == target_ref
                    and (r.get("label") or "").strip() == label
                ),
                None,
            )
            if existing is not None:
                changed = {k: v for k, v in fields.items() if existing.get(k) != v}
                if changed:
                    self.patch.setdefault("relationships", []).append(
                        {"id": existing["id"], **changed}
                    )
                    self.changes.append(f"人物関係 {title}を更新")
                continue
            key = self._new_key(NEW_RELATIONSHIP_KEY)
            new = {"key": key, "source": source_ref, "target": target_ref, "label": label, **fields}
            self.relationships.append(new)
            self.patch.setdefault("relationships", []).append(new)
            self.new_relationships.append(key)
            self.changes.append(f"人物関係 {title}を追加")

    def outcome(self, link_to_dramaturgy: bool) -> PatchOutcome:
        patch: dict[str, Any] = dict(self.patch)
        if link_to_dramaturgy:
            # 作品の参照の一覧は丸ごと置き換わるので、今の参照に足して渡す
            dramaturgy_patch: dict[str, Any] = {}
            refs = [r["ref"] for r in self.dramaturgy.get("characters", [])]
            added = [k for k in self.mentioned_characters if k not in refs]
            if added:
                dramaturgy_patch["characters"] = [{"ref": k} for k in [*refs, *added]]
            relationship_refs = [r["ref"] for r in self.dramaturgy.get("relationships", [])]
            if self.new_relationships:
                dramaturgy_patch["relationships"] = [
                    {"ref": k} for k in [*relationship_refs, *self.new_relationships]
                ]
            if dramaturgy_patch and (patch or added):
                patch["dramaturgies"] = [{"id": self.dramaturgy["id"], **dramaturgy_patch}]
                if added and not any(c.startswith("人物「") for c in self.changes):
                    self.changes.append("登録済みの人物をこの作品の登場人物に加える")
        return PatchOutcome(patch or None, self.changes, self.warnings)


def world_patch(
    content: dict[str, Any],
    dramaturgy_id: str,
    task_code: str,
    characters: list[CharacterDraft],
    groups: list[GroupDraft],
    relationships: list[RelationshipDraft],
) -> PatchOutcome:
    """人物・まとまり・人物関係の提案を部分YAMLにする(追加と更新だけ)。task_codeは工程のタスク。"""
    world = _World(content, dramaturgy_id)
    is_characters = task_code == "create_character"
    world.add_characters(characters)
    world.add_groups(groups, keep_members=is_characters)
    world.add_relationships(relationships)
    return world.outcome(link_to_dramaturgy=is_characters or task_code == "create_relationship")


# ---------------------------------------------------------------------------
# 配役・声
# ---------------------------------------------------------------------------


def _dramaturgy_spec(content: dict[str, Any], dramaturgy_id: str) -> dict[str, Any]:
    return next(d for d in content.get("dramaturgies", []) if d.get("id") == dramaturgy_id)


def _character_names(content: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {c["name"].strip(): c for c in content.get("characters", []) if c.get("name")}


def _cast_by_character_key(dramaturgy: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {c["character"]["ref"]: c for c in dramaturgy.get("casts", []) if c.get("character")}


def cast_patch(content: dict[str, Any], dramaturgy_id: str, drafts: list[CastDraft]) -> PatchOutcome:
    """配役の提案を部分YAMLにする(追加と更新だけ)。"""
    dramaturgy = _dramaturgy_spec(content, dramaturgy_id)
    characters = _character_names(content)
    casts = _cast_by_character_key(dramaturgy)
    patches: list[dict[str, Any]] = []
    changes: list[str] = []
    warnings: list[str] = []
    character_refs = [r["ref"] for r in dramaturgy.get("characters", [])]
    added_refs: list[str] = []
    for index, draft in enumerate(drafts):
        name = (draft.character or "").strip()
        if not name:
            continue
        character = characters.get(name)
        if character is None:
            warnings.append(f"配役の人物「{name}」がいないので、外しました(先にCharactersの工程で人物を作ってください)。")
            continue
        fields: dict[str, Any] = _compact(
            {"language": _text(draft.language), "accent": _text(draft.accent)}
        )
        billing = _text(draft.billing)
        if billing is not None:
            if billing in {b.value for b in CastBilling}:
                fields["billing"] = billing
            else:
                warnings.append(f"「{name}」の役の重さ「{billing}」は決まりに無いので、外しました。")
        gender = _text(draft.voice_gender)
        if gender is not None:
            if gender in {g.value for g in VoiceGender}:
                fields["voice_gender"] = gender
            else:
                warnings.append(f"「{name}」の声の性別「{gender}」は決まりに無いので、外しました。")
        performance = _compact(
            {
                "title": _text(draft.performance_title),
                "description": _text(draft.performance_description),
                "pace": _text(draft.pace),
            }
        )
        if performance:
            fields["performance"] = performance
        existing = casts.get(character["key"])
        if existing is not None:
            current_performance = existing.get("performance") or {}
            changed = {
                k: v
                for k, v in fields.items()
                if (k == "performance" and {**current_performance, **v} != current_performance)
                or (k != "performance" and existing.get(k) != v)
            }
            if changed:
                patches.append({"id": existing["id"], **changed})
                changes.append(f"「{name}」の配役を更新")
        else:
            key = f"{NEW_CAST_KEY}{index + 1}"
            casts[character["key"]] = {"key": key, "character": {"ref": character["key"]}}
            patches.append({"key": key, "character": {"ref": character["key"]}, **fields})
            label = BILLING_LABELS.get(fields.get("billing", ""), "")
            changes.append(f"「{name}」の配役を追加" + (f"({label})" if label else ""))
        if character["key"] not in character_refs and character["key"] not in added_refs:
            added_refs.append(character["key"])
    if not patches:
        return PatchOutcome(None, [], warnings)
    dramaturgy_patch: dict[str, Any] = {"id": dramaturgy_id, "casts": patches}
    if added_refs:
        # 作品の参照の一覧は丸ごと置き換わるので、今の参照に足して渡す
        dramaturgy_patch["characters"] = [{"ref": k} for k in [*character_refs, *added_refs]]
        changes.append("配役した人物をこの作品の登場人物に加える")
    return PatchOutcome({"dramaturgies": [dramaturgy_patch]}, changes, warnings)


def audition_patch(
    content: dict[str, Any],
    dramaturgy_id: str,
    choices: list[VoiceChoice],
    voices: list[VoiceInfo],
    tts_provider: str,
    tts_model: str,
) -> PatchOutcome:
    """選んだ声を、配役ごとの演者(Actor)の話者・提供元・モデルにする部分YAML。演者がいなければ作る。"""
    dramaturgy = _dramaturgy_spec(content, dramaturgy_id)
    characters = _character_names(content)
    casts = _cast_by_character_key(dramaturgy)
    by_id = {v.voice_id: v for v in voices}
    actors = {a["cast"]["ref"]: a for a in (dramaturgy.get("agents") or {}).get("actors", []) if a.get("cast")}
    patches: list[dict[str, Any]] = []
    changes: list[str] = []
    warnings: list[str] = []
    for index, choice in enumerate(choices):
        name = (choice.character or "").strip()
        voice_id = (choice.voice_id or "").strip()
        if not (name and voice_id):
            continue
        character = characters.get(name)
        cast = casts.get(character["key"]) if character else None
        if cast is None:
            warnings.append(f"「{name}」の配役が無いので、声を外しました(先にCastingの工程で配役を作ってください)。")
            continue
        voice = by_id.get(voice_id)
        if voice is None:
            warnings.append(f"「{name}」の声「{voice_id}」は声の一覧に無いので、外しました。")
            continue
        fields = {"voice_name": voice_id, "tts_provider": tts_provider, "tts_model": tts_model}
        label = f"{voice_id}" + (f"({voice.display_name})" if voice.display_name else "")
        existing = actors.get(cast["key"])
        if existing is not None:
            changed = {k: v for k, v in fields.items() if existing.get(k) != v}
            if changed:
                patches.append({"id": existing["id"], **changed})
                changes.append(f"「{name}」の声を{label}にする")
        else:
            patches.append(
                {"key": f"{NEW_ACTOR_KEY}{index + 1}", "name": f"{name}役の演者", "cast": {"ref": cast["key"]}, **fields}
            )
            changes.append(f"「{name}」の演者を作り、声を{label}にする")
    if not patches:
        return PatchOutcome(None, [], warnings)
    return PatchOutcome(
        {"dramaturgies": [{"id": dramaturgy_id, "agents": {"actors": patches}}]}, changes, warnings
    )
