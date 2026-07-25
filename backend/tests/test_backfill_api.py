"""MT-24: in-app mileage backfill (pending fills + gallons-weighted suggestion)."""

from conftest import connect, run_migrations, seed_fillup, seed_vehicle


# --- migration ---------------------------------------------------------------


def test_migration_makes_mileage_nullable_and_preserves_rows(tmp_path):
    """A v2 DB with data migrates to v3 keeping every row; mileage becomes
    nullable while UNIQUE(vehicle_id, mileage) still allows multiple NULLs."""
    db_path = tmp_path / "v2.db"
    conn = connect(db_path)
    # Build the pre-0003 schema by applying only 0001 + 0002.
    conn.executescript(
        "CREATE TABLE vehicles (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE,"
        " make TEXT, model TEXT, year INTEGER, tank_size_gal REAL,"
        " created_at TEXT NOT NULL DEFAULT (datetime('now')));"
        "CREATE TABLE fillups (id INTEGER PRIMARY KEY,"
        " vehicle_id INTEGER NOT NULL REFERENCES vehicles(id),"
        " date TEXT NOT NULL, mileage INTEGER NOT NULL CHECK (mileage > 0),"
        " gallons REAL NOT NULL, cost REAL, station TEXT, zip TEXT,"
        " missed_last_fill INTEGER NOT NULL DEFAULT 0,"
        " created_at TEXT NOT NULL DEFAULT (datetime('now')),"
        " mileage_estimated INTEGER NOT NULL DEFAULT 0, gauge_notches REAL,"
        " UNIQUE (vehicle_id, mileage));"
        "PRAGMA user_version = 2;"
    )
    vid = seed_vehicle(conn, name="Tiger")
    # Raw inserts against the hand-built pre-migration schema (the seed_fillup
    # helper targets the current schema, which has columns this table lacks yet).
    conn.executemany(
        "INSERT INTO fillups (vehicle_id, date, mileage, gallons, cost)"
        " VALUES (?, ?, ?, 10.0, 30.0)",
        [(vid, "2023-01-01", 1000), (vid, "2023-01-10", 1300)],
    )
    conn.commit()
    before = conn.execute("SELECT COUNT(*) FROM fillups").fetchone()[0]

    assert run_migrations(conn) == 4  # 0003 (nullable) + 0004 (partial_fill)
    assert conn.execute("SELECT COUNT(*) FROM fillups").fetchone()[0] == before

    # mileage is now nullable and multiple NULLs coexist under the UNIQUE.
    conn.execute(
        "INSERT INTO fillups (vehicle_id, date, mileage, gallons, cost)"
        " VALUES (?, ?, NULL, 10.0, 30.0)",
        (vid, "2023-01-15"),
    )
    conn.execute(
        "INSERT INTO fillups (vehicle_id, date, mileage, gallons, cost)"
        " VALUES (?, ?, NULL, 10.0, 30.0)",
        (vid, "2023-01-16"),
    )
    conn.commit()
    assert conn.execute(
        "SELECT COUNT(*) FROM fillups WHERE mileage IS NULL"
    ).fetchone()[0] == 2
    conn.close()


# --- pending creation --------------------------------------------------------


def _seed_two_real(conn):
    """Vehicle with real fills at 1000 (Jan 1) and 1600 (Jan 20)."""
    vid = seed_vehicle(conn, tank_size_gal=13.0)
    seed_fillup(conn, vid, 1000, date="2023-01-01", gallons=10.0)
    seed_fillup(conn, vid, 1600, date="2023-01-20", gallons=10.0)
    return vid


def test_post_null_mileage_creates_pending_row(conn, client):
    vid = _seed_two_real(conn)
    resp = client.post(
        "/api/fillups",
        json={
            "vehicle_id": vid,
            "date": "2023-01-10",
            "mileage": None,
            "gallons": 10.0,
            "cost": 30.0,
            "station": "Shell",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["mileage"] is None
    assert body["mileage_estimated"] is False
    assert body["mpf"] is None
    assert body["mpg"] is None
    # Bracketed by 1000 (Jan 1) and 1600 (Jan 20): weights (10, 10) -> midpoint.
    assert body["suggested_mileage"] == 1300


def test_post_omitted_mileage_creates_pending_row(conn, client):
    vid = _seed_two_real(conn)
    resp = client.post(
        "/api/fillups",
        json={"vehicle_id": vid, "date": "2023-01-10", "gallons": 10.0, "cost": 30.0},
    )
    assert resp.status_code == 201
    assert resp.json()["mileage"] is None


def test_pending_row_listed_first_with_null_derivation(conn, client):
    vid = _seed_two_real(conn)
    client.post(
        "/api/fillups",
        json={"vehicle_id": vid, "date": "2023-01-10", "gallons": 10.0, "cost": 30.0},
    )
    body = client.get(f"/api/fillups?vehicle_id={vid}").json()
    assert body["total"] == 3  # count includes the pending row
    items = body["items"]
    # Pending row appears first; real rows follow by mileage DESC.
    assert items[0]["mileage"] is None
    assert items[0]["mpf"] is None and items[0]["mpg"] is None
    assert items[0]["suggested_mileage"] == 1300
    assert [i["mileage"] for i in items[1:]] == [1600, 1000]


def test_real_row_derivation_unchanged_by_pending(conn, client):
    """A pending row must not corrupt real rows' prev_mileage derivation."""
    vid = _seed_two_real(conn)
    seed_fillup(conn, vid, 1300, date="2023-01-10", gallons=10.0)  # real middle
    baseline = client.get(f"/api/fillups?vehicle_id={vid}").json()["items"]
    baseline_mpg = {i["mileage"]: i["mpg"] for i in baseline}

    client.post(  # add a pending fill in the same window
        "/api/fillups",
        json={"vehicle_id": vid, "date": "2023-01-12", "gallons": 10.0, "cost": 30.0},
    )
    after = client.get(f"/api/fillups?vehicle_id={vid}").json()["items"]
    after_mpg = {i["mileage"]: i["mpg"] for i in after if i["mileage"] is not None}
    assert after_mpg == baseline_mpg  # real derivation untouched


# --- suggested_mileage edge cases -------------------------------------------


def test_suggested_null_when_unbracketed_trailing(conn, client):
    vid = _seed_two_real(conn)
    resp = client.post(  # dated after the last real fill -> no "after" anchor
        "/api/fillups",
        json={"vehicle_id": vid, "date": "2023-02-01", "gallons": 10.0, "cost": 30.0},
    )
    assert resp.json()["suggested_mileage"] is None


def test_suggested_null_when_no_prior_real_fill(conn, client):
    vid = seed_vehicle(conn, tank_size_gal=13.0)
    seed_fillup(conn, vid, 1600, date="2023-01-20", gallons=10.0)  # only a later fill
    resp = client.post(
        "/api/fillups",
        json={"vehicle_id": vid, "date": "2023-01-05", "gallons": 10.0, "cost": 30.0},
    )
    assert resp.json()["suggested_mileage"] is None


def test_suggested_consecutive_pair_splits_proportionally(conn, client):
    """MT-21 reference bracket: 68186 -> 69038 with gallons weights
    (10.753, 9.212, 11.304) yields exactly 68479 and 68730."""
    vid = seed_vehicle(conn, tank_size_gal=13.0)
    seed_fillup(conn, vid, 68186, date="2024-01-01", gallons=11.0)
    seed_fillup(conn, vid, 69038, date="2024-01-15", gallons=11.304)
    client.post(
        "/api/fillups",
        json={"vehicle_id": vid, "date": "2024-01-05", "gallons": 10.753, "cost": 43.0},
    )
    client.post(
        "/api/fillups",
        json={"vehicle_id": vid, "date": "2024-01-10", "gallons": 9.212, "cost": 33.15},
    )
    body = client.get(f"/api/fillups?vehicle_id={vid}").json()
    by_date = {i["date"]: i for i in body["items"] if i["mileage"] is None}
    assert by_date["2024-01-05"]["suggested_mileage"] == 68479
    assert by_date["2024-01-10"]["suggested_mileage"] == 68730


# --- resolve-mileage ---------------------------------------------------------


def _make_pending(conn, client, vid, date="2023-01-10", gallons=10.0):
    resp = client.post(
        "/api/fillups",
        json={"vehicle_id": vid, "date": date, "gallons": gallons, "cost": 30.0},
    )
    return resp.json()["id"]


def test_resolve_happy_path_sets_estimate_and_derives_mpg(conn, client):
    vid = _seed_two_real(conn)
    pid = _make_pending(conn, client, vid)
    resp = client.post(f"/api/fillups/{pid}/resolve-mileage", json={"mileage": 1300})
    assert resp.status_code == 200
    body = resp.json()
    assert body["mileage"] == 1300
    assert body["mileage_estimated"] is True
    assert body["suggested_mileage"] is None  # no longer pending
    # Derived MPG now materializes: (1300-1000)/10 = 30.0.
    assert body["mpf"] == 300
    assert body["mpg"] == 30.0
    assert body["mpg_estimated"] is True  # rests on an estimated odometer

    # It now sorts among real rows and the next row's derivation shifts too.
    items = client.get(f"/api/fillups?vehicle_id={vid}").json()["items"]
    assert [i["mileage"] for i in items] == [1600, 1300, 1000]
    assert items[0]["mpf"] == 300  # 1600 - 1300


def test_resolve_rejects_value_outside_bracket(conn, client):
    vid = _seed_two_real(conn)
    pid = _make_pending(conn, client, vid)
    for bad in (1000, 999, 1600, 1601):
        resp = client.post(f"/api/fillups/{pid}/resolve-mileage", json={"mileage": bad})
        assert resp.status_code == 422, bad


def test_resolve_404_for_unknown_id(client):
    resp = client.post("/api/fillups/999/resolve-mileage", json={"mileage": 1000})
    assert resp.status_code == 404


def test_resolve_409_for_non_pending_row(conn, client):
    vid = _seed_two_real(conn)
    real_id = conn.execute(
        "SELECT id FROM fillups WHERE vehicle_id = ? AND mileage = 1600", (vid,)
    ).fetchone()[0]
    resp = client.post(f"/api/fillups/{real_id}/resolve-mileage", json={"mileage": 1500})
    assert resp.status_code == 409


def test_resolve_422_when_unbracketed(conn, client):
    vid = _seed_two_real(conn)
    pid = _make_pending(conn, client, vid, date="2023-02-01")  # trailing, no "after"
    resp = client.post(f"/api/fillups/{pid}/resolve-mileage", json={"mileage": 1700})
    assert resp.status_code == 422
