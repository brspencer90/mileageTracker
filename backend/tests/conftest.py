"""Test fixtures — all run against the isolated `mileageTracker_test` database.

The test connection string is derived from the repo-root `.env` `sqlss_conn_str`
by swapping the database name to `mileageTracker_test` (the production
`mileageTracker` DB is NEVER touched). Each test gets a clean slate: rows are
deleted (fillups before vehicles, for the FK) and identity is reseeded to 0 so
id-based assertions hold.
"""

import re
from pathlib import Path

import pyodbc
import pytest
from fastapi.testclient import TestClient

from app.db import connect, run_schema

_ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"


def _raw_test_conn_str() -> str:
    text = _ROOT_ENV.read_text(encoding="utf-8")
    m = re.search(r"sqlss_conn_str\s*=\s*['\"]?(.*?)['\"]?\s*$", text, re.M)
    if not m:
        raise RuntimeError("sqlss_conn_str not found in repo-root .env")
    cs = re.sub(r"DATABASE=\{[^}]*\}", "DATABASE={mileageTracker_test}", m.group(1))
    # Safety: refuse to run unless we are unambiguously on the test database.
    assert "DATABASE={mileageTracker_test}" in cs, cs
    return cs


_RAW = _raw_test_conn_str()
_FULL = f"DRIVER={{ODBC Driver 18 for SQL Server}};{_RAW};TrustServerCertificate=Yes"


def _clean(conn: pyodbc.Connection) -> None:
    cur = conn.cursor()
    cur.execute("SELECT DB_NAME()")
    assert cur.fetchone()[0] == "mileageTracker_test"  # belt-and-suspenders
    cur.execute("DELETE FROM fillups")
    cur.execute("DELETE FROM vehicles")
    cur.execute("DBCC CHECKIDENT('fillups', RESEED, 0)")
    cur.execute("DBCC CHECKIDENT('vehicles', RESEED, 0)")
    conn.commit()


@pytest.fixture(autouse=True)
def _prepare_db():
    """Apply the schema (idempotent) and wipe/reseed before every test."""
    conn = connect(_FULL)
    run_schema(conn)
    _clean(conn)
    conn.close()
    yield


@pytest.fixture
def conn():
    conn = connect(_FULL)
    yield conn
    conn.close()


@pytest.fixture
def client(monkeypatch):
    # Point the app's config at the test DB; a real env var overrides .env.
    monkeypatch.setenv("sqlss_conn_str", _RAW)
    from app.main import create_app

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def seed_vehicle(
    conn: pyodbc.Connection, name: str = "TestCar", tank_size_gal: float | None = None
) -> int:
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO vehicles (name, tank_size_gal) OUTPUT INSERTED.id VALUES (?, ?)",
        name, tank_size_gal,
    )
    vid = cur.fetchone()[0]
    conn.commit()
    return vid


def seed_fillup(
    conn: pyodbc.Connection,
    vehicle_id: int,
    mileage: int | None,
    *,
    date: str = "2023-01-01",
    gallons: float = 10.0,
    cost: float | None = 30.0,
    station: str | None = None,
    zip_code: str | None = None,
    missed_last_fill: bool = False,
    mileage_estimated: bool = False,
    gauge_notches: float | None = None,
    partial_fill: bool = False,
) -> int:
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO fillups"
        " (vehicle_id, [date], mileage, gallons, cost, station, zip,"
        "  missed_last_fill, mileage_estimated, gauge_notches, partial_fill)"
        " OUTPUT INSERTED.id"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            vehicle_id,
            date,
            mileage,
            gallons,
            cost,
            station,
            zip_code,
            1 if missed_last_fill else 0,
            1 if mileage_estimated else 0,
            gauge_notches,
            1 if partial_fill else 0,
        ),
    )
    fid = cur.fetchone()[0]
    conn.commit()
    return fid
