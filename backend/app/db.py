"""SQL Server (pyodbc) connection helper and schema runner (no ORM)."""

import re
from pathlib import Path

import pyodbc
from fastapi import Request

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def connect(conn_str: str) -> pyodbc.Connection:
    """Open a pyodbc connection (autocommit off; callers commit explicitly)."""
    return pyodbc.connect(conn_str, timeout=8)


def run_schema(conn: pyodbc.Connection) -> None:
    """Apply schema.sql (idempotent CREATE-if-not-exists) via a batch runner.

    pyodbc runs one statement per ``execute``, so split the file into statements
    on blank lines. Comment-only lines are dropped first so a leading comment
    never swallows the statement that follows it.
    """
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
    stmts = [s.strip() for s in re.split(r"\n\s*\n", "\n".join(lines)) if s.strip()]
    cur = conn.cursor()
    for stmt in stmts:
        cur.execute(stmt)
    conn.commit()


def get_db(request: Request):
    """FastAPI dependency: one connection per request.

    Autocommit is off; write query functions commit themselves, so the teardown
    just closes. A commit here on clean exit is harmless and covers any writer
    that forgot to commit.
    """
    conn = connect(request.app.state.conn_str)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
