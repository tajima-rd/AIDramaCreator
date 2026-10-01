# core/model/drama/feature.py
"""
特徴(Characteristic)と、その中の項目(AdditionalFeature)。固定の属性(名前・年齢等)に加えるもので、必要な項目はテーマや
作品の種類で変わるので、項目を決め打ちにせず、item(項目)と値で書く。2階層まで(Characteristicの中にAdditionalFeature)。
現状は人物(Character.characteristics)が使う。
"""

from typing import Optional


class AdditionalFeature:
    """特徴の中の1つの項目。itemは項目、valueはその値。definitionはitemが何を意味するか(空でもよいが、架空の言葉等では意味の定義を書く)。
    descriptionは補足の説明。"""

    def __init__(
        self,
        item: str,
        value: Optional[str] = None,
        definition: Optional[str] = None,
        description: Optional[str] = None,
    ):
        self.item: str = item
        self.value: Optional[str] = value
        self.definition: Optional[str] = definition
        self.description: Optional[str] = description


class Characteristic:
    """特徴(項目のまとまり。例: 職業とキャリア)。item・definition・descriptionの意味はAdditionalFeatureと同じ。"""

    def __init__(
        self,
        item: str,
        definition: Optional[str] = None,
        description: Optional[str] = None,
        features: Optional[list[AdditionalFeature]] = None,
    ):
        self.item: str = item
        self.definition: Optional[str] = definition
        self.description: Optional[str] = description
        self.features: list[AdditionalFeature] = list(features or [])
