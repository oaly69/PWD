from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import db
from .config import VERSION, settings
from .routers import admin, assets, auth, chat, generate, install, prompts, providers, system, users
from .seed import seed_if_upgraded
from .services import tasks

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("pwd")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if db.engine is None:
        db.init_engine()
    tasks.recover_interrupted()
    with db.new_session() as session:
        seed_if_upgraded(session)
    log.info("PWD %s 已启动，数据目录：%s", VERSION, settings.data_dir)
    if settings.install_token:
        log.info("已启用安装令牌保护（PWD_INSTALL_TOKEN）")
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="PWD - 个人 AIGC 创作平台", version=VERSION, lifespan=lifespan, docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json")

    for r in (system.router, install.router, auth.router, providers.router, chat.router, generate.router, assets.router, prompts.router, users.router, admin.router):
        app.include_router(r)

    static_dir = settings.static_dir
    index = static_dir / "index.html"
    if (static_dir / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="static-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith(("api/", "media/")):
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = (static_dir / full_path).resolve()
        if full_path and candidate.is_relative_to(static_dir.resolve()) and candidate.is_file():
            return FileResponse(candidate)
        if index.is_file():
            return FileResponse(index, headers={"Cache-Control": "no-cache"})
        return JSONResponse({"message": "前端尚未构建，请访问 /api/docs 或先构建 frontend"}, status_code=200)

    return app


app = create_app()
