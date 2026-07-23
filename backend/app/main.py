"""App factory: routers, health check, migration-at-startup, static serving."""

import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings
from .db import connect, get_db, run_migrations
from .routers import fillups, stats, vehicles


def create_app() -> FastAPI:
    settings = Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        conn = connect(settings.db_path)
        try:
            run_migrations(conn)
        finally:
            conn.close()
        yield

    app = FastAPI(title="Mileage Tracker", lifespan=lifespan)
    app.state.db_path = settings.db_path

    @app.get("/api/health")
    def health(conn: sqlite3.Connection = Depends(get_db)):
        conn.execute("SELECT 1").fetchone()
        return {"status": "ok"}

    # /api routers are registered before the SPA catch-all, so they always win.
    app.include_router(vehicles.router)
    app.include_router(fillups.router)
    app.include_router(stats.router)

    dist = Path(settings.static_dir)
    if dist.is_dir():  # skip static serving when there is no built SPA (dev mode)
        assets = dist / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            """Serve real files at the dist root (manifest, sw.js, registerSW.js,
            icons); anything else falls back to index.html (SPA fallback)."""
            root = dist.resolve()
            target = (dist / path).resolve()
            if path and target.is_file() and target.is_relative_to(root):
                return FileResponse(target)
            return FileResponse(dist / "index.html")

    return app


app = create_app()
