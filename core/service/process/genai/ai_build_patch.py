# core/service/process/genai/ai_build_patch.py
"""
Build with AIの生成AIの提案を、編集用の下書きへ重ねる部分YAML(docs/database_design.md「部分YAMLの重ね合わせ」)にする。
工程ごとの規則は docs/architecture.md 10節。

- 企画書(Proposal): 対話は変わった項目だけ(空で返した項目は変えない)、ワンショットは丸ごと置き換え(空の項目は消す)
- 人物・まとまり・人物関係(Characters・Groups・Relationships): 追加と更新だけで、削除はしない。既存の要素は名前で対応付ける
  (人物=名前、まとまり=名前、人物関係=起点・相手の人物と関係の名前)。空の値では既存の値を消さない。名前の分からない人物を
  指すメンバー・関係は外して、注意として返す。Charactersの工程で出てきた人物と、新しく作った人物関係は、作品の参照にも加える
"""

from typing import Any, Optional

from core.model.drama import Dramaturgy
from core.prompt.ai_build.characters import CharacterDraft, GroupDraft, RelationshipDraft
from core.prompt.ai_build.common import BuildMode
from core.prompt.ai_build.proposal import ProposalReply

# 提案の中で新しい要素を参照するためのkeyの接頭辞(下書きのkeyは種類と通し番号なので重ならない)
NEW_CHARACTER_KEY = "ai_character_"
NEW_GROUP_KEY = "ai_group_"
NEW_RELATIONSHIP_KEY = "ai_relationship_"


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
