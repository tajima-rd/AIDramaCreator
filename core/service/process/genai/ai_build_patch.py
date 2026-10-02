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
"""

from typing import Any, Optional

from core.genai import VoiceInfo
from core.model.drama import CastBilling, Dramaturgy, VoiceGender
from core.prompt.ai_build.casting import BILLING_LABELS, CastDraft, VoiceChoice
from core.prompt.ai_build.characters import CharacterDraft, GroupDraft, RelationshipDraft
from core.prompt.ai_build.common import BuildMode
from core.prompt.ai_build.proposal import ProposalReply

# 提案の中で新しい要素を参照するためのkeyの接頭辞(下書きのkeyは種類と通し番号なので重ならない)
NEW_CHARACTER_KEY = "ai_character_"
NEW_GROUP_KEY = "ai_group_"
NEW_RELATIONSHIP_KEY = "ai_relationship_"
NEW_CAST_KEY = "ai_cast_"
NEW_ACTOR_KEY = "ai_actor_"


class PatchOutcome:
    """patchは部分YAMLの対応表(変わる所が無ければNone)、changesは利用者に見せる変更の一覧、warningsは提案から外したものの注意。"""

    def __init__(self, patch: Optional[dict[str, Any]], changes: list[str], warnings: list[str]):
        self.patch: Optional[dict[str, Any]] = patch
        self.changes: list[str] = changes
        self.warnings: list[str] = warnings


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
