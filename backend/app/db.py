"""SQLite connection helper and migration runner (no ORM, no migration library)."""

import re
import sqlite3
from pathlib import Path

from fastapi import Request

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_MIGRATION_RE = re.compile(r"^(\d{4})_.+\.sql$")


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open a connection with the standard pragmas; auto-create the parent dir."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: FastAPI may run a sync dependency's setup,
    # the endpoint, and teardown on different threadpool threads. Each
    # connection is still used by exactly one request at a time.
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def run_migrations(conn: sqlite3.Connection) -> int:
    """Apply migrations/000N_*.sql for N > PRAGMA user_version, in order.

    Returns the resulting schema version.
    """
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    for path in sorted(MIGRATIONS_DIR.iterdir()):
        m = _MIGRATION_RE.match(path.name)
        if not m:
            continue
        n = int(m.group(1))
        if n <= version:
            continue
        conn.executescript(path.read_text(encoding="utf-8"))
        conn.execute(f"PRAGMA user_version = {n}")
        conn.commit()
        version = n
    return version


def get_db(request: Request):
    """FastAPI dependency: one connection per request."""
    conn = connect(request.app.state.db_path)
    try:
        yield conn
    finally:
        conn.close()
