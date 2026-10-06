# core/schema/formats/dramaturgy_definition.py
"""
Dramaturgy(core.model.drama)を宣言する「モデル定義YAML」の形。作品が1つならdramaturgyに、複数(プロジェクトの作品モデル全体。
DBの版・下書きの写し。docs/architecture.md 7節)ならdramaturgiesの一覧に書く(両方に書いてもよく、dramaturgyが先頭になる)。読み書きはcore.infra.io.
model_definition_reader・model_definition_writer。準備の各項目(前提・人物・配役・プロット)の取り込みと、
生成AIとの受け渡しに使う(docs/model_design.md)。

【区画】モデルのコンポジション(所有)は、YAMLでも入れ子にする。作品が所有しない要素(TemporalNode・Location・SiteFlow・
Character・CharacterGroup・Relationship)は、dramaturgyと並ぶ最上位の区画に書き、参照する(人物・人物関係・場所・移動の持ち主はProjectで、作品は参照で持つ)。作品作りに参加するエージェント(core.model.agent)は、
作品が所有するので、dramaturgyの中のagentsに職能ごとに書く(作品ごとに役割・厳守事項等を書き換えられる。2026-10-01)。

    protocol_version: "0.1.0"   # 省略可
    temporal_nodes: [{id, key, label, date_type, string_date}]
    locations: [{id, key, name, geometry, address, instruction, description}]   # geometryはWKT(WGS84、経度・緯度の順)
    site_flows: [{id, key, name, geometry, direction, origin, destination}]   # 場所の間の移動。origin/destinationはLocationへの参照、
                                                                             # geometryはWKTのLINESTRING、directionはforward・backward・both
    characters: [{id, key, name, reading, gender, age,
                  speech_style: {first_person, tone, description,
                                 endings: [{kind, examples: [...], description}]},   # kindはnormal・conjecture等
                  characteristics: [{item, definition, description,
                                     features: [{item, value, definition, description}]}],
                  biographies: [{id, key, period, episode, involved_relationships: [...]}]}]
    character_groups: [{id, key, name, kind, members: [{ref}], description}]   # 人物のまとまり(kindは自由に書く)
    relationships: [{id, key, source, target, label, period, description, form_of_address, tone}]   # source/targetはCharacterへの参照
    dramaturgy:
      id, key, title, synopsis, input_language, output_language
      premise: {text}
      proposal: {title, catchphrase, logline, intent, target_area, synopsis,   # 企画書(初期シード。題・あらすじ・人物は作品と共有しない)
                 characters: [{name, description}]}                          # 企画書の登場人物(仮の設定。Characterとは別)
      characters: [{ref}]             # この作品に関わる人物(参照。人物はdramaturgyの外にある)
      relationships: [{ref}]          # この作品に関わる人物関係(参照)
      locations: [{ref}]              # この作品で使う場所(参照)
      site_flows: [{ref}]             # この作品で使う移動(参照)
      casts: [{id, key, character, performance: {title, description, pace}, voice_gender, language, accent, billing}]   # voice_genderはmale・female・neutral、
                                                                                                                # billingはlead(主役)・supporting(脇役)・minor(端役)
      acts: [{id, key, order, title, synopsis,
              scenes: [{id, key, order, title, synopsis, period, location,
                        situation: {location, description, time_of_day, environment},
                        script: {lines: [{id, key, order, cast, text}]},
                        elements: [{type: dialogue, id, key, order, line, cast, text, action, direction,
                                    translations: [{language, text}], situation}   # translationsは言語ごとの訳文(同じ言語は1つ)
                                   | {type: sound_effect | atmosphere | music, id, key, order}]}]}]
      history: {edges: [{id, key, label, kind, source, target}]}   # source/targetはTemporalNodeへの参照
      agents:                         # 作品作りに参加するエージェント(生成AIが担う職能。作品が所有する)
        researchers | casting_directors | scriptwriters | directors | stage_managers | sound_engineers:
          [{id, key, name, role, persona, rules: [...], prohibitions: [...],
            tasks: [{code, title, description, rules: [...], prohibitions: [...]}]}]
        actors: [{同上, cast, voice_name, tts_provider, tts_model}]   # castはCastへの参照(モデルではActor.casting_id)。音声合成の提供元・モデル・話者
    dramaturgies: [{dramaturgyと同じ形}]   # 作品が複数のとき

【エージェントの既定値】role・rules・prohibitionsを省略すれば職能の既定(core.model.agentの各クラス)。書けば(空の一覧[]も)
その値。tasksは職能ごとに決まったタスク(code)のうち、書き換えたものだけを書けばよく、省略したタスクと、タスクの中で
省略した項目は既定になる。職能に無いcodeはエラー。書き出しでは、既定と同じでもすべてを書く(作品ごとの全文を残す)。

【分割】1つのファイル(複数のYAML文書を`---`で区切ってもよい)にも、複数のファイルにも書ける。分けた文書は、
どれも上と同じ入れ子の形で、その一部だけを書く(例: 人物だけのファイルは`dramaturgy: {characters: [...]}`)。
読むときはすべての文書を重ね合わせる: 対応表は同じキーどうしを重ね、一覧はidかkeyが同じ要素どうしを重ね、
それ以外の要素は読んだ順につなげる。同じ値(titleやid等)を2つの文書に書くときは、同じでなければならない。
例えばシーンは属する幕を、台詞(script)は属する幕とシーンを、idかkeyで示せば、別のファイルに書ける:

    dramaturgy:
      acts:
        - key: act_001
          scenes:
            - key: scene_001
              script:
                lines: [...]

分けて書くときは、幕・シーンのorderを書いておくのがよい(省略すると、重ね合わせた後の並びの位置になり、ファイルを読む順に左右される)。

【識別子と参照】(2026-10-01ユーザー決定: すべて id / key / ref の方式)
- id: エンティティの識別子(UUID)。システムが決める(人・生成AIには決めさせない)。書けばその識別子を保ち、
  無ければ読むときにシステムが振る(core.model.identifier)。書き出しでは常に書く。
- key: このYAML一式の中だけで使う呼び名。参照の受け口で、モデルには残らない。書き出しでは種類と通し番号
  (character_001・cast_001・scene_001_line_001等)を付ける。
- 参照(source・target・period・location・origin・destination・character・cast・line・involved_relationshipsの各要素)は、
  常に {ref: 参照先のkey}。idでは参照しない。参照先は同じYAML一式の中になければならず、種類ごとに探す
  (TemporalNode・Location・SiteFlow・Character・Relationship・Cast・Line)。
- order: 省略すれば、並びの中の位置(0から)。
"""

from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from core.model.drama.cast import CastBilling, VoiceGender
from core.model.drama.site_flow import SiteFlowDirection
from core.model.drama.speech_style import SentenceEndingKind
from core.model.drama.temporal import StringDateType, TemporalRelationKind

PROTOCOL_VERSION = "0.1.0"


class _Spec(BaseModel):
    # 書き誤り(属性名の綴り等)を黙って捨てない
    model_config = ConfigDict(extra="forbid")


class Ref(_Spec):
    """参照。refは参照先のkey(同じYAML一式の中)。"""

    ref: str


class PremiseSpec(_Spec):
    text: Optional[str] = None


class ProposalCharacterSpec(_Spec):
    name: Optional[str] = None
    description: Optional[str] = None


class ProposalSpec(_Spec):
    """企画書(core.model.drama.proposal)。すべて省略できる。"""

    title: Optional[str] = None
    catchphrase: Optional[str] = None
    logline: Optional[str] = None
    intent: Optional[str] = None
    target_area: Optional[str] = None
    synopsis: Optional[str] = None
    characters: list[ProposalCharacterSpec] = []


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
    source: Ref  # TemporalNodeへの参照
    target: Ref  # TemporalNodeへの参照


class HistorySpec(_Spec):
    edges: list[TemporalEdgeSpec] = []


class LocationSpec(_Spec):
    id: Optional[str] = None
    key: Optional[str] = None
    name: str
    geometry: Optional[str] = None  # WKT(WGS84、経度・緯度の順)
    address: Optional[str] = None
    instruction: Optional[str] = None
    description: Optional[str] = None


class SiteFlowSpec(_Spec):
    id: Optional[str] = None
    key: Optional[str] = None
    name: Optional[str] = None
    geometry: Optional[str] = None  # WKTのLINESTRING。始点はoriginの面、終点はdestinationの面の中
    direction: Optional[SiteFlowDirection] = None  # 線を引いた向き(origin→destination)に対する移動の向き
    origin: Ref  # Locationへの参照
    destination: Ref  # Locationへの参照


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
    key: Optional[str] = None
    period: Ref  # TemporalNodeへの参照
    episode: str
    involved_relationships: list[Ref] = []  # Relationshipへの参照


class SentenceEndingSpec(_Spec):
    kind: SentenceEndingKind
    examples: list[str] = []
    description: Optional[str] = None


class SpeechStyleSpec(_Spec):
    first_person: Optional[str] = None
    tone: Optional[str] = None
    endings: list[SentenceEndingSpec] = []
    description: Optional[str] = None


class CharacterSpec(_Spec):
    id: Optional[str] = None
    key: Optional[str] = None
    name: str
    reading: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[str] = None
    speech_style: Optional[SpeechStyleSpec] = None
    characteristics: list[CharacteristicSpec] = []
    biographies: list[BiographySpec] = []


class CharacterGroupSpec(_Spec):
    id: Optional[str] = None
    key: Optional[str] = None
    name: str
    kind: Optional[str] = None  # 自由に書く(例: 家族・職場)
    members: list[Ref] = []  # Characterへの参照
    description: Optional[str] = None


class RelationshipSpec(_Spec):
    id: Optional[str] = None
    key: Optional[str] = None
    source: Ref  # Characterへの参照
    target: Ref  # Characterへの参照
    label: str
    period: Optional[Ref] = None  # TemporalNodeへの参照
    description: Optional[str] = None
    form_of_address: Optional[str] = None
    tone: Optional[str] = None


class PerformanceSpec(_Spec):
    title: Optional[str] = None
    description: Optional[str] = None
    pace: Optional[str] = None


class CastSpec(_Spec):
    id: Optional[str] = None
    key: Optional[str] = None
    character: Ref  # Characterへの参照
    performance: Optional[PerformanceSpec] = None
    voice_gender: Optional[VoiceGender] = None
    language: Optional[str] = None
    accent: Optional[str] = None
    billing: Optional[CastBilling] = None  # 役の重さ(lead=主役・supporting=脇役・minor=端役)


class LineSpec(_Spec):
    id: Optional[str] = None
    key: Optional[str] = None
    order: Optional[int] = None
    cast: Ref  # Castへの参照
    text: str


class ScriptSpec(_Spec):
    lines: list[LineSpec] = []


class DirectionSpec(_Spec):
    style: Optional[str] = None
    pace: Optional[str] = None
    dynamics: Optional[str] = None
    emotion: Optional[str] = None
    pause_after: Optional[str] = None


class SituationSpec(_Spec):
    location: Optional[Ref] = None  # Locationへの参照
    description: Optional[str] = None
    time_of_day: Optional[str] = None
    environment: Optional[str] = None


class TranslationSpec(_Spec):
    language: str  # 言語のコード(BCP 47。例: en・zh-CN)
    text: str


class DialogueSpec(_Spec):
    type: Literal["dialogue"]
    id: Optional[str] = None
    key: Optional[str] = None
    order: Optional[int] = None
    line: Ref  # Lineへの参照(モデルではDialogue.line_id)
    cast: Ref  # Castへの参照(モデルではDialogue.cast_id)
    text: str
    action: Optional[str] = None
    direction: Optional[DirectionSpec] = None
    translations: list[TranslationSpec] = []  # 言語ごとの訳文(同じ言語は1つ)
    situation: Optional[SituationSpec] = None  # 場面の途中で変わるときだけ


class SoundEffectSpec(_Spec):
    type: Literal["sound_effect"]
    id: Optional[str] = None
    key: Optional[str] = None
    order: Optional[int] = None


class AtmosphereSpec(_Spec):
    type: Literal["atmosphere"]
    id: Optional[str] = None
    key: Optional[str] = None
    order: Optional[int] = None


class MusicSpec(_Spec):
    type: Literal["music"]
    id: Optional[str] = None
    key: Optional[str] = None
    order: Optional[int] = None


ScriptElementSpec = Annotated[
    Union[DialogueSpec, SoundEffectSpec, AtmosphereSpec, MusicSpec],
    Field(discriminator="type"),
]


class SceneSpec(_Spec):
    id: Optional[str] = None
    key: Optional[str] = None
    order: Optional[int] = None
    title: Optional[str] = None
    synopsis: Optional[str] = None
    period: Optional[Ref] = None  # TemporalNodeへの参照
    location: Optional[Ref] = None  # Locationへの参照
    situation: Optional[SituationSpec] = None
    script: Optional[ScriptSpec] = None
    elements: list[ScriptElementSpec] = []


class ActSpec(_Spec):
    id: Optional[str] = None
    key: Optional[str] = None
    order: Optional[int] = None
    title: Optional[str] = None
    synopsis: Optional[str] = None
    scenes: list[SceneSpec] = []


class AgentTaskSpec(_Spec):
    """エージェントのタスク(core.model.agent.AgentTask)。codeで職能のタスクを特定し、省略した項目は既定。"""

    code: str
    title: Optional[str] = None
    description: Optional[str] = None
    rules: Optional[list[str]] = None
    prohibitions: Optional[list[str]] = None


class AgentSpec(_Spec):
    """role・rules・prohibitionsは省略すれば職能の既定(空の一覧[]と区別する)。"""

    id: Optional[str] = None
    key: Optional[str] = None
    name: str
    role: Optional[str] = None
    persona: Optional[str] = None
    rules: Optional[list[str]] = None
    prohibitions: Optional[list[str]] = None
    tasks: list[AgentTaskSpec] = []


class LanguageVoiceSpec(_Spec):
    language: str  # 言語のコード(BCP 47。例: en・zh-CN)
    voice_name: str  # その言語を読むときの話者
    tts_provider: Optional[str] = None  # 空なら演者の既定(それも空ならproject.yamlのgenai.tts)
    tts_model: Optional[str] = None


class ActorSpec(AgentSpec):
    cast: Ref  # Castへの参照(モデルではActor.casting_id)
    voice_name: Optional[str] = None  # 既定の話者(音声合成の提供元の声の識別子)
    tts_provider: Optional[str] = None  # 音声合成の提供元(例: Gemini)。空ならproject.yamlのgenai.tts
    tts_model: Optional[str] = None  # 音声合成のモデル。空ならproject.yamlのgenai.tts
    voices: list[LanguageVoiceSpec] = []  # 言語ごとの声(その言語を読むときに既定の声の代わりに使う。同じ言語は1つ)


class AgentsSpec(_Spec):
    """職能ごとのエージェント。区画名は職能の複数形(core.model.agent.factory.AGENT_ROLESの名前+s)。"""

    researchers: list[AgentSpec] = []
    casting_directors: list[AgentSpec] = []
    scriptwriters: list[AgentSpec] = []
    directors: list[AgentSpec] = []
    stage_managers: list[AgentSpec] = []
    sound_engineers: list[AgentSpec] = []
    actors: list[ActorSpec] = []


class DramaturgySpec(_Spec):
    id: Optional[str] = None
    key: Optional[str] = None
    title: str
    synopsis: Optional[str] = None
    input_language: Optional[str] = None
    output_language: Optional[str] = None
    premise: Optional[PremiseSpec] = None
    proposal: Optional[ProposalSpec] = None  # 企画書
    characters: list[Ref] = []  # 人物への参照
    relationships: list[Ref] = []  # 人物関係への参照
    locations: list[Ref] = []  # 場所への参照
    site_flows: list[Ref] = []  # 移動への参照
    casts: list[CastSpec] = []
    acts: list[ActSpec] = []
    history: Optional[HistorySpec] = None
    agents: Optional[AgentsSpec] = None  # 作品作りに参加するエージェント


class DramaturgyDefinition(_Spec):
    """モデル定義YAMLの全体(分割したファイルを重ね合わせた後)。"""

    protocol_version: Literal["0.1.0"] = PROTOCOL_VERSION
    temporal_nodes: list[TemporalNodeSpec] = []
    locations: list[LocationSpec] = []
    site_flows: list[SiteFlowSpec] = []
    characters: list[CharacterSpec] = []
    character_groups: list[CharacterGroupSpec] = []
    relationships: list[RelationshipSpec] = []
    dramaturgy: Optional[DramaturgySpec] = None
    dramaturgies: list[DramaturgySpec] = []  # 作品が複数のとき(プロジェクトの作品モデル全体)
