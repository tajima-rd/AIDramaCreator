# api/routers/_http.py
"""
複数のrouterで共有する、例外→HTTPステータスの対応付けの補助(内部用)。

プロジェクト・Datasetの不在は、api/main.pyの共通の例外ハンドラが404へ
対応付ける。ここにあるのは、エンドポイントごとの意味に応じて各routerが使い分ける分。
"""

from fastapi import HTTPException

_BAD_REQUEST = (KeyError, ValueError)
_BAD_ITEM_REQUEST = (KeyError, ValueError, TypeError)


def _bad_request(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def _not_found(exc: Exception) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))
