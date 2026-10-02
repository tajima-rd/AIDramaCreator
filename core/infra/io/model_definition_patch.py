# core/infra/io/model_definition_patch.py
"""
部分YAML(モデル定義YAMLの形で、変えたい部分だけを書いたもの)を、モデル定義(重ね合わせた後の対応表)に重ねる
(docs/database_design.md「部分YAMLの重ね合わせ」)。下書きのApply・直接編集・取り込みが使う。

- 一覧の要素は、idがあればidで、無ければkeyで同じ要素を探して重ねる。無ければ末尾に追加する。
- 同じ場所の値は上書きする。nullを書くと、その属性を消す。
- idもkeyも持たない一覧(_REPLACED_LISTS。作品の中ではcharacters・relationships・locations・site_flows、企画書の中ではcharactersも)は、
  書いた一覧で丸ごと置き換える。
- {id: …, delete: true}(keyでも可)で要素を消す。所有している子も一緒に消える。
- dramaturgy(単数)は、dramaturgiesの1要素として扱う。

ここでは対応表を重ねるだけで、形の検証と参照の解決はしない(重ねた後にmodel_definition_readerで組み立てる)。
"""

import copy
from typing import Any, Optional

# idもkeyも持たない要素の一覧(書いた一覧で丸ごと置き換える)。rules・prohibitions・tasksはエージェントとそのタスクの
# 一覧(タスクはcodeで特定するが、一覧ごと送る)
_REPLACED_LISTS = frozenset(
    {
        "members",
        "involved_relationships",
        "characteristics",
        "features",
        "endings",
        "examples",
        "rules",
        "prohibitions",
        "tasks",
    }
)
# 区画ごとに、丸ごと置き換える一覧(区画の名前→一覧の名前)。作品(dramaturgy)の中のcharacters・relationships・locations・
# site_flowsは参照の一覧(最上位では人物・人物関係・場所・移動そのものの一覧)。企画書(proposal)のcharactersは識別子の無い仮の登場人物
_REPLACED_IN_SECTION = {
    "dramaturgy": frozenset({"characters", "relationships", "locations", "site_flows"}),
    "proposal": frozenset({"characters"}),
}

DELETE = "delete"


def patch_spec(base: dict[str, Any], documents: list[Optional[dict[str, Any]]]) -> dict[str, Any]:
    """baseに部分YAMLの文書を順に重ねた、新しい対応表を返す(baseは変えない。後の文書が上書きする)。"""
    result = _with_dramaturgies(copy.deepcopy(base or {}), "重ねる先")
    for document in documents:
        if document is None:
            continue
        if not isinstance(document, dict):
            raise ValueError("部分YAMLの文書は、区画名をキーにした対応表でなければなりません")
        _patch_map(result, _with_dramaturgies(copy.deepcopy(document), "部分YAML"), "", None)
    return result


def _with_dramaturgies(spec: dict[str, Any], where: str) -> dict[str, Any]:
    """dramaturgy(単数)を、dramaturgiesの先頭の要素にする。"""
    if spec.get("dramaturgy") is not None:
        dramaturgies = spec.get("dramaturgies") or []
        if not isinstance(dramaturgies, list):
            raise ValueError(f"{where}のdramaturgiesは一覧でなければなりません")
        spec["dramaturgies"] = [spec.pop("dramaturgy"), *dramaturgies]
    else:
        spec.pop("dramaturgy", None)
    return spec


def _patch_map(
    target: dict[str, Any], patch: dict[str, Any], path: str, section: Optional[str]
) -> None:
    """sectionは対応表が属する区画("dramaturgy"・"proposal"。それ以外はNone)。"""
    for key, value in patch.items():
        where = f"{path}.{key}" if path else str(key)
        if value is None:
            target.pop(key, None)
        elif isinstance(value, list) and (
            key in _REPLACED_LISTS or key in _REPLACED_IN_SECTION.get(section, frozenset())
        ):
            target[key] = value
        elif isinstance(value, list) and isinstance(target.get(key), list):
            _patch_list(target[key], value, where, key == "dramaturgies")
        elif isinstance(value, list):
            target[key] = []
            _patch_list(target[key], value, where, key == "dramaturgies")
        elif isinstance(value, dict) and isinstance(target.get(key), dict):
            inner = "proposal" if section == "dramaturgy" and key == "proposal" else None
            _patch_map(target[key], value, where, inner)
        else:
            _check_no_delete(value, where)
            target[key] = value


def _patch_list(target: list[Any], items: list[Any], path: str, dramaturgies: bool) -> None:
    """idかkeyで要素を特定して重ねる。特定できなければ末尾に足す。"""
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"'{path}' の要素は対応表でなければなりません")
        name = item.get("id") or item.get("key")
        where = f"{path}[{name}]" if name else path
        same = _find(target, item)
        if item.get(DELETE) is True:
            if same is None:
                raise ValueError(f"'{where}' を消そうとしましたが、その要素がありません")
            target.remove(same)
            continue
        item = {key: value for key, value in item.items() if key != DELETE}
        if same is None:
            _check_no_delete(item, where)
            target.append(item)
        else:
            _patch_map(same, item, where, "dramaturgy" if dramaturgies else None)


def _find(items: list[Any], item: dict[str, Any]) -> Optional[dict[str, Any]]:
    """idがあればidで、無ければkeyで同じ要素を探す。"""
    name = "id" if item.get("id") is not None else "key"
    if item.get(name) is None:
        return None
    for existing in items:
        if isinstance(existing, dict) and existing.get(name) == item[name]:
            return existing
    return None


def _check_no_delete(value: Any, where: str) -> None:
    """新しく足す部分の中に、削除の印があってはならない(消す相手がいない)。"""
    if isinstance(value, dict):
        if value.get(DELETE) is True:
            raise ValueError(f"'{where}' の中に削除の印がありますが、消す要素がありません")
        for key, child in value.items():
            _check_no_delete(child, f"{where}.{key}")
    elif isinstance(value, list):
        for child in value:
            _check_no_delete(child, where)
