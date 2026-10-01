# core/schema/formats/dramaturgy_definition.py
"""
1つのDramaturgy(core.model.drama)を宣言する「モデル定義YAML」の形。読み書きはcore.infra.io.
model_definition_reader・model_definition_writer。準備の各項目(前提・人物・配役・プロット)の取り込みと、
生成AIとの受け渡しに使う(docs/model_design.md)。

【区画】モデルのコンポジション(所有)は、YAMLでも入れ子にする。所有者を持たない要素(TemporalNode・Location・
Relationship)は、dramaturgyと並ぶ最上位の区画に書き、参照する。

    protocol_version: "0.1.0"   # 省略可
    temporal_nodes: [{id, key, label, date_type, string_date}]
    locations: [{id, key, name, latitude, longitude, address, instruction, description}]
    relationships: [{id, key, source, target, label, period, description}]   # source/targetはCharacterへの参照
    dramaturgy:
      id, title, synopsis, input_language, output_language
      premise: {text}
      characters: [{id, key, name, reading, gender, age, speech_style,
                    characteristics: [{item, definition, description,
                                       features: [{item, value, definition, description}]}],
                    biographies: [{id, period, episode, involved_relationship}]}]
      casts: [{id, key, character, provider, voice_name, language, accent, notes}]
      acts: [{id, key, order, title, synopsis,
              scenes: [{id, key, order, title, synopsis, period, location,
                        script: {lines: [{id, key, order, cast, text}]},
                        elements: [{type: dialogue, id, order, line, cast, text, action, direction, translated_text}
                                   | {type: sound_effect | atmosphere | music, id, order}]}]}]
      history: {edges: [{id, key, label, kind, source, target}]}   # source/targetはTemporalNodeへの参照

【分割】1つのファイル(複数のYAML文書を`---`で区切ってもよい)にも、複数のファイルにも書ける。分けた文書は、
どれも上と同じ入れ子の形で、その一部だけを書く(例: 人物だけのファイルは`dramaturgy: {characters: [...]}`)。
読むときはすべての文書を重ね合わせる: 対応表は同じキーどうしを重ね、一覧はidかkeyが同じ要素どうしを重ね、
それ以外の要素は読んだ順につなげる。同じ値(titleやid等)を2つの文書に書くときは、同じでなければならない。
例えばシーンは属する幕を、台詞(script)は属する幕とシーンを、idかkeyで示せば、別のファイルに書ける:

    dramaturgy:
      acts:
        - key: act1          # または id
          scenes:
            - key: scene1    # または id
              script:
                lines: [...]

分けて書くときは、幕・シーンのorderを書いておくのがよい(省略すると、重ね合わせた後の並びの位置になり、ファイルを読む順に左右される)。

【識別子と参照】
- id: エンティティの識別子(UUID)。書けばその識別子を保ち、省略すれば新しく振る(core.model.identifier)。
  書き出しでは常に書く(往復で識別子を保つため)。
- key: この定義の中だけで使う参照の名前(省略可)。人や生成AIがidを決めずに書くためのもので、モデルには残らない。
- 参照(source・target・period・location・character・cast・line・involved_relationship)は、参照先のkeyかid。
  参照先は種類ごとに探す(TemporalNode・Location・Character・Relationship・Cast・Line)。
- order: 省略すれば、並びの中の位置(0から)。
"""

from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from core.model.drama.temporal import StringDateType, TemporalRelationKind

PROTOCOL_VERSION = "0.1.0"


class _Spec(BaseModel):
    # 書き誤り(属性名の綴り等)を黙って捨てない
    model_config = ConfigDict(extra="forbid")


class PremiseSpec(_Spec):
    text: Optional[str] = None


class TemporalNodeSpec(_Spec):
    id: Optional[str] = None
    key: Optional[str] = None
    label: Optional[str] = None
    date_type: Optional[StringDateType] = None
    string_date: Optional[str] = None


class TemporalEdgeSpec(_Spec):
    id: Optional[str] = None
    key: Optional[str] = None
    label: Optional[str] = None
    kind: TemporalRelationKind
    source: str  # TemporalNodeへの参照
    target: str  # TemporalNodeへの参照


class HistorySpec(_Spec):
    edges: list[TemporalEdgeSpec] = []


class LocationSpec(_Spec):
    id: Optional[str] = None
    key: Optional[str] = None
    name: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    address: Optional[str] = None
    instruction: Optional[str] = None
    description: Optional[str] = None


class AdditionalFeatureSpec(_Spec):
    item: str
    value: Optional[str] = None
    definition: Optional[str] = None
    description: Optional[str] = None


class CharacteristicSpec(_Spec):
    item: str
    definition: Optional[str] = None
    description: Optional[str] = None
    features: list[AdditionalFeatureSpec] = []


class BiographySpec(_Spec):
    id: Optional[str] = None
    period: str  # TemporalNodeへの参照
    episode: str
    involved_relationship: Optional[str] = None  # Relationshipへの参照


class CharacterSpec(_Spec):
    id: Optional[str] = None
    key: Optional[str] = None
    name: str
    reading: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[str] = None
    speech_style: Optional[str] = None
    characteristics: list[CharacteristicSpec] = []
    biographies: list[BiographySpec] = []


class RelationshipSpec(_Spec):
    id: Optional[str] = None
    key: Optional[str] = None
    source: str  # Characterへの参照
    target: str  # Characterへの参照
    label: str
    period: Optional[str] = None  # TemporalNodeへの参照
    description: Optional[str] = None


class CastSpec(_Spec):
    id: Optional[str] = None
    key: Optional[str] = None
    character: str  # Characterへの参照
    provider: Optional[str] = None
    voice_name: Optional[str] = None
    language: Optional[str] = None
    accent: Optional[str] = None
    notes: Optional[str] = None


class LineSpec(_Spec):
    id: Optional[str] = None
    key: Optional[str] = None
    order: Optional[int] = None
    cast: str  # Castへの参照
    text: str


class ScriptSpec(_Spec):
    lines: list[LineSpec] = []


class DirectionSpec(_Spec):
    style: Optional[str] = None
    pace: Optional[str] = None
    dynamics: Optional[str] = None
    emotion: Optional[str] = None
    pause_after: Optional[str] = None


class DialogueSpec(_Spec):
    type: Literal["dialogue"]
    id: Optional[str] = None
    order: Optional[int] = None
    line: str  # Lineへの参照(モデルではDialogue.line_id)
    cast: str  # Castへの参照(モデルではDialogue.cast_id)
    text: str
    action: Optional[str] = None
    direction: Optional[DirectionSpec] = None
    translated_text: Optional[str] = None


class SoundEffectSpec(_Spec):
    type: Literal["sound_effect"]
    id: Optional[str] = None
    order: Optional[int] = None


class AtmosphereSpec(_Spec):
    type: Literal["atmosphere"]
    id: Optional[str] = None
    order: Optional[int] = None


class MusicSpec(_Spec):
    type: Literal["music"]
    id: Optional[str] = None
    order: Optional[int] = None


ScriptElementSpec = Annotated[
    Union[DialogueSpec, SoundEffectSpec, AtmosphereSpec, MusicSpec],
    Field(discriminator="type"),
]


class SceneSpec(_Spec):
    id: Optional[str] = None
    key: Optional[str] = None  # 参照はされない。分けたファイル(台詞等)がどのシーンに属するかを示す
    order: Optional[int] = None
    title: Optional[str] = None
    synopsis: Optional[str] = None
    period: Optional[str] = None  # TemporalNodeへの参照
    location: Optional[str] = None  # Locationへの参照
    script: Optional[ScriptSpec] = None
    elements: list[ScriptElementSpec] = []


class ActSpec(_Spec):
    id: Optional[str] = None
    key: Optional[str] = None  # 参照はされない。分けたファイル(シーン等)がどの幕に属するかを示す
    order: Optional[int] = None
    title: Optional[str] = None
    synopsis: Optional[str] = None
    scenes: list[SceneSpec] = []


class DramaturgySpec(_Spec):
    id: Optional[str] = None
    title: str
    synopsis: Optional[str] = None
    input_language: Optional[str] = None
    output_language: Optional[str] = None
    premise: Optional[PremiseSpec] = None
    characters: list[CharacterSpec] = []
    casts: list[CastSpec] = []
    acts: list[ActSpec] = []
    history: Optional[HistorySpec] = None


class DramaturgyDefinition(_Spec):
    """モデル定義YAMLの全体(分割したファイルを重ね合わせた後)。"""

    protocol_version: Literal["0.1.0"] = PROTOCOL_VERSION
    temporal_nodes: list[TemporalNodeSpec] = []
    locations: list[LocationSpec] = []
    relationships: list[RelationshipSpec] = []
    dramaturgy: DramaturgySpec
