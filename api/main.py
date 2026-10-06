# api/main.py
"""
core/service/api の処理をローカルで実行するためのAPI層。

責務は「渡されたデータ・パラメータを処理して結果を返す」ことのみ。

プロジェクト(project.yaml + project.db + datasets/ から成るディレクトリ単位のコンテナ)を
複数同時に相手にするため、プロジェクトに属するエンドポイントは/projects/{project_id}/配下に置く。
project_idはcore.infra.store.project_registry_store(永続レジストリ)で管理し、「一度作ったら
明示的に消すまで有効」という扱いにする(サーバーのメモリ上の一時的なセッションにはしない)。

1エンドポイントはcore/service/apiの1つの処理に対応させ、複数の処理の結果
を1つのエンドポイントにまとめない(パイプラインの組み立てはクライアント
側の責務)。

リクエスト/レスポンスはJSONではなくYAMLでやり取りする(api/yaml_io.py)。
型定義はcore/schema/を参照。

エンドポイント本体は、core.service.apiと同じリソース単位でapi/routers/配下に分割されている
(include順は、ルートの照合順を保つため変更しないこと)。このファイルは
FastAPIアプリの生成・各routerのinclude・静的ファイルのmount・システム側の例外から
HTTPステータスへの共通の対応付けのみを担う。Web GUI(apps/AIDC-Console)は/app/で配信する(/は/app/へ転送する)。

システム(core/service/api)はHTTPを知らず、エラーを例外で返す。プロジェクト・Dataset・作品モデルの下書きと版の不在は
専用の例外(ProjectNotFoundError・DatasetNotFoundError・DatasetMetadataNotFoundError・DraftNotFoundError・
VersionNotFoundError)なので、
ここで一律に404へ対応付ける。それ以外(KeyError/ValueError→400等)は、エンドポイントごとの
意味に応じて各routerで対応付ける。
"""

import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from api.routers import (
    agent_default,
    ai_build,
    character_import,
    dataset,
    drama_draft,
    drama_model,
    language,
    preference,
    project,
    recording,
    scene_translation,
    voice,
)
from core.project.dataset import DatasetMetadataNotFoundError, DatasetNotFoundError
from core.project.project import ProjectNotFoundError
from core.service.api.drama_draft import DraftNotFoundError
from core.service.api.drama_model import VersionNotFoundError

app = FastAPI(title="AIDramaCreator API")
app.include_router(project.router)
app.include_router(preference.router)
app.include_router(dataset.router)
app.include_router(drama_model.router)
app.include_router(drama_draft.router)
app.include_router(agent_default.router)
app.include_router(ai_build.router)
app.include_router(character_import.router)
app.include_router(voice.router)
app.include_router(language.router)
app.include_router(recording.router)
app.include_router(scene_translation.router)


@app.exception_handler(ProjectNotFoundError)
async def project_not_found(_request: Request, _exc: ProjectNotFoundError):
    return JSONResponse(status_code=404, content={"detail": "project not found"})


@app.exception_handler(DatasetNotFoundError)
async def dataset_not_found(_request: Request, _exc: DatasetNotFoundError):
    return JSONResponse(status_code=404, content={"detail": "dataset not found"})


@app.exception_handler(DatasetMetadataNotFoundError)
async def dataset_metadata_not_found(_request: Request, _exc: DatasetMetadataNotFoundError):
    return JSONResponse(status_code=404, content={"detail": "dataset metadata not found"})


@app.exception_handler(DraftNotFoundError)
async def draft_not_found(_request: Request, exc: DraftNotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(VersionNotFoundError)
async def version_not_found(_request: Request, exc: VersionNotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/app/")


_CONSOLE_APP_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "apps", "AIDC-Console")
app.mount("/app", StaticFiles(directory=_CONSOLE_APP_DIR, html=True), name="aidc-console")
