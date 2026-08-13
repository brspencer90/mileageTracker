"""App factory: routers, health check, migration-at-startup, static serving."""

import os
from contextlib import asynccontextmanager
from pathlib import Path

import pyodbc

# Build stamp: CI passes the commit SHA as a build-arg -> env var; "dev" locally.
# Lets you confirm which image is actually live after a deploy (docs/DEPLOY_SYNOLOGY.md).
GIT_SHA = os.environ.get("GIT_SHA", "dev")

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings
from .db import connect, get_db, run_schema
from .routers import fillups, stats, vehicles


def _safe_target(conn_str: str) -> str:
    """The SERVER/DATABASE tokens from the ODBC string, for logging — never the
    password. Confirms *what* a failing startup was pointed at."""
    parts = [
        p.strip() for p in conn_str.split(";")
        if p.strip().upper().startswith(("SERVER=", "DATABASE="))
    ]
    return " ".join(parts) or "(no server in conn str)"


def create_app() -> FastAPI:
    settings = Settings()
    conn_str = settings.pyodbc_conn_str()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Logged BEFORE the DB connect so a crash-loop still shows which build is
        # running and what it tried to reach (troubleshooting: is this the new image?).
        print(f"[mileage-tracker] startup build={GIT_SHA} -> {_safe_target(conn_str)}",
              flush=True)
        conn = connect(conn_str)
        try:
            run_schema(conn)
        finally:
            conn.close()
        print(f"[mileage-tracker] ready build={GIT_SHA} (schema applied)", flush=True)
        yield

    app = FastAPI(title="Mileage Tracker", lifespan=lifespan)
    app.state.conn_str = conn_str

    @app.get("/api/health")
    def health(conn: pyodbc.Connection = Depends(get_db)):
        # SELECT 1 makes the healthcheck verify the DB dependency, not just "up".
        conn.execute("SELECT 1").fetchone()
        return {"status": "ok", "version": GIT_SHA}

    @app.get("/api/version")
    def version():
        return {"version": GIT_SHA}

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
