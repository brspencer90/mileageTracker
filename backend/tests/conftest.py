import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.db import connect, run_migrations


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture
def conn(db_path):
    conn = connect(db_path)
    run_migrations(conn)
    yield conn
    conn.close()


@pytest.fixture
def client(db_path, monkeypatch):
    monkeypatch.setenv("MT_DB_PATH", str(db_path))
    from app.main import create_app

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def seed_vehicle(
    conn: sqlite3.Connection, name: str = "TestCar", tank_size_gal: float | None = None
) -> int:
    cur = conn.execute(
        "INSERT INTO vehicles (name, tank_size_gal) VALUES (?, ?)",
        (name, tank_size_gal),
    )
    conn.commit()
    return cur.lastrowid


def seed_fillup(
    conn: sqlite3.Connection,
    vehicle_id: int,
    mileage: int,
    *,
    date: str = "2023-01-01",
    gallons: float = 10.0,
    cost: float = 30.0,
    station: str | None = None,
    zip_code: str | None = None,
    missed_last_fill: bool = False,
    mileage_estimated: bool = False,
    gauge_notches: float | None = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO fillups"
        " (vehicle_id, date, mileage, gallons, cost, station, zip,"
        "  missed_last_fill, mileage_estimated, gauge_notches)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
        ),
    )
    conn.commit()
    return cur.lastrowid
