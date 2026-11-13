from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from backend.app.config import settings
from backend.app.database import init_db
from backend.app.routers import (
    dashboard,
    downloads,
    imports,
    library,
    logs,
    search,
    settings as settings_router,
    sources,
)
from backend.app.services.download_manager import download_manager
from backend.app.services.logger_service import log_event


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.ensure_directories()
    init_db()
    log_event("INFO", "SYSTEM", "OpenMusic Archive Manager backend started.")
    await download_manager.recover_pending_jobs()
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Self-hosted music discovery, lossless verification, and download management "
        "application for Navidrome."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard.router)
app.include_router(imports.router)
app.include_router(search.router)
app.include_router(downloads.router)
app.include_router(library.router)
app.include_router(sources.router)
app.include_router(settings_router.router)
app.include_router(logs.router)


@app.get("/api/v1/health")
def health_check() -> Dict[str, Any]:
    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": settings.app_version,
    }


# Serve compiled React frontend if built in frontend/dist
FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api/"):
            return {"detail": "Not Found"}
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.exists() and candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(FRONTEND_DIST / "index.html"))
