# core/model/identifier.py
"""
エンティティの識別子(UUID)。プロジェクト(project_id)・Dataset(file_id)等は、生成時にこの形式のidを持ち、
以後変わらない(名前は変更できる)。DBの主キーと参照、APIのパスはこのidでエンティティを指す。
"""

import uuid


def new_id() -> str:
    """新しい識別子(ハイフン区切りのUUID文字列。project_id・run_id等と同じ形式)。"""
    return str(uuid.uuid4())
