# api/yaml_io.py
"""
api/ のリクエスト/レスポンスをYAMLでやり取りするためのヘルパー。

FastAPIの標準機構(pydanticモデルを引数に取ると自動でJSONボディとして
解釈される)はJSON専用のため使わず、生のリクエストボディをYAMLとして
読み、レスポンスもYAML文字列として組み立てる。
"""

from enum import Enum

import numpy as np
import yaml
from fastapi import Request
from fastapi.responses import Response
from pydantic import BaseModel

YAML_MEDIA_TYPE = "application/yaml"


class _Dumper(yaml.SafeDumper):
    """SafeDumperに、core/service/api側がよく返すnumpyスカラー型・(Dataset
    ProvenanceProcess等の)str Enumへの対応を加えたもの。"""


_Dumper.add_multi_representer(np.generic, lambda dumper, data: dumper.represent_data(data.item()))
_Dumper.add_multi_representer(Enum, lambda dumper, data: dumper.represent_data(data.value))


async def parse_yaml_body[T: BaseModel](request: Request, model: type[T]) -> T:
    raw = await request.body()
    data = yaml.safe_load(raw.decode("utf-8")) or {}
    return model.model_validate(data)


async def read_text_body(request: Request) -> str:
    """リクエストの本文を、検証せずに文字列のまま読む(部分YAML等、型に当てはめずに渡すもの)。"""
    return (await request.body()).decode("utf-8")


def yaml_response(model: BaseModel, exclude_unset: bool = False) -> Response:
    """modelをYAMLで返す。exclude_unsetなら、値を指定した属性だけを書く(モデル定義YAMLの形を返すとき)。"""
    text = yaml.dump(
        model.model_dump(exclude_unset=exclude_unset),
        Dumper=_Dumper,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    )
    return Response(content=text, media_type=YAML_MEDIA_TYPE)
