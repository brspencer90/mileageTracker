from datetime import date, timedelta

from conftest import seed_fillup, seed_vehicle


def seed_basic(conn, tank_size_gal=13.0):
    """Vehicle with three fill-ups at 1000/1300/1600."""
    vehicle_id = seed_vehicle(conn, tank_size_gal=tank_size_gal)
    seed_fillup(conn, vehicle_id, 1000, date="2023-01-01", station="Kroger", zip_code="77077")
    seed_fillup(conn, vehicle_id, 1300, date="2023-01-10", station="Shell", zip_code="77007")
    seed_fillup(conn, vehicle_id, 1600, date="2023-01-20", station="Costco", zip_code="77055")
    return vehicle_id


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body  # build stamp (GIT_SHA; "dev" outside CI)


def test_version(client):
    resp = client.get("/api/version")
    assert resp.status_code == 200
    assert "version" in resp.json()


def test_vehicles_list(conn, client):
    vehicle_id = seed_vehicle(conn, name="Tiger", tank_size_gal=13.0)
    resp = client.get("/api/vehicles")
    assert resp.status_code == 200
    body = resp.json()
    assert body == [
        {
            "id": vehicle_id,
            "name": "Tiger",
            "make": None,
            "model": None,
            "year": None,
            "tank_size_gal": 13.0,
        }
    ]


def test_list_fillups_ordered_and_paginated(conn, client):
    vehicle_id = seed_basic(conn)
    resp = client.get(f"/api/fillups?vehicle_id={vehicle_id}&limit=2&offset=0")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert [item["mileage"] for item in body["items"]] == [1600, 1300]  # mileage DESC
    assert body["items"][0]["mpf"] == 300
    assert body["items"][0]["mpg"] == 30.0


def test_create_happy_path_returns_derived(conn, client):
    vehicle_id = seed_basic(conn)
    resp = client.post(
        "/api/fillups",
        json={
            "vehicle_id": vehicle_id,
            "date": "2023-02-01",
            "mileage": 1900,
            "gallons": 12.0,
            "cost": 36.006,
            "station": "Kroger",
            "zip": "77077",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["mpf"] == 300
    assert body["mpg"] == 25.0
    assert body["cost"] == 36.01  # rounded at the API boundary
    assert body["missed_last_fill"] is False
    assert body["id"] > 0


def test_create_first_fillup_has_null_derivation(conn, client):
    vehicle_id = seed_vehicle(conn)
    resp = client.post(
        "/api/fillups",
        json={
            "vehicle_id": vehicle_id,
            "date": "2023-01-01",
            "mileage": 334,
            "gallons": 11.571,
            "cost": 29.61,
            "missed_last_fill": True,
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["mpf"] is None
    assert body["mpg"] is None


def test_create_rejects_mileage_not_above_max(conn, client):
    vehicle_id = seed_basic(conn)
    for bad_mileage in (1600, 1450):
        resp = client.post(
            "/api/fillups",
            json={
                "vehicle_id": vehicle_id,
                "date": "2023-02-01",
                "mileage": bad_mileage,
                "gallons": 10.0,
                "cost": 30.0,
            },
        )
        assert resp.status_code == 422
        assert "1600" in resp.json()["detail"]


def test_create_rejects_future_date(conn, client):
    vehicle_id = seed_basic(conn)
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    resp = client.post(
        "/api/fillups",
        json={
            "vehicle_id": vehicle_id,
            "date": tomorrow,
            "mileage": 1900,
            "gallons": 10.0,
            "cost": 30.0,
        },
    )
    assert resp.status_code == 422
    assert "future" in resp.json()["detail"].lower()


def test_create_rejects_gallons_over_tank_cap(conn, client):
    vehicle_id = seed_basic(conn, tank_size_gal=13.0)  # cap = 14.3
    resp = client.post(
        "/api/fillups",
        json={
            "vehicle_id": vehicle_id,
            "date": "2023-02-01",
            "mileage": 1900,
            "gallons": 14.31,
            "cost": 45.0,
        },
    )
    assert resp.status_code == 422
    assert "14.3" in resp.json()["detail"]


def test_create_allows_big_gallons_without_tank_size(conn, client):
    vehicle_id = seed_vehicle(conn, tank_size_gal=None)
    resp = client.post(
        "/api/fillups",
        json={
            "vehicle_id": vehicle_id,
            "date": "2023-02-01",
            "mileage": 100,
            "gallons": 25.0,
            "cost": 80.0,
        },
    )
    assert resp.status_code == 201


def test_create_rejects_bad_zip(conn, client):
    vehicle_id = seed_basic(conn)
    resp = client.post(
        "/api/fillups",
        json={
            "vehicle_id": vehicle_id,
            "date": "2023-02-01",
            "mileage": 1900,
            "gallons": 10.0,
            "cost": 30.0,
            "zip": "1234",
        },
    )
    assert resp.status_code == 422  # pydantic pattern


def test_create_unknown_vehicle_404(client):
    resp = client.post(
        "/api/fillups",
        json={
            "vehicle_id": 999,
            "date": "2023-02-01",
            "mileage": 100,
            "gallons": 10.0,
            "cost": 30.0,
        },
    )
    assert resp.status_code == 404


def test_patch_mileage_within_neighbor_bounds(conn, client):
    vehicle_id = seed_basic(conn)
    middle_id = conn.execute(
        "SELECT id FROM fillups WHERE vehicle_id = ? AND mileage = 1300",
        (vehicle_id,),
    ).fetchone()[0]

    for bad_mileage in (1000, 999, 1600, 1601):
        resp = client.patch(f"/api/fillups/{middle_id}", json={"mileage": bad_mileage})
        assert resp.status_code == 422, bad_mileage

    resp = client.patch(f"/api/fillups/{middle_id}", json={"mileage": 1450})
    assert resp.status_code == 200
    assert resp.json()["mpf"] == 450
    assert resp.json()["mpg"] == 45.0

    # The following row's derivation shifts too, proving derive-at-read.
    listing = client.get(f"/api/fillups?vehicle_id={vehicle_id}").json()
    top = listing["items"][0]
    assert top["mileage"] == 1600
    assert top["mpf"] == 150


def test_patch_other_fields(conn, client):
    vehicle_id = seed_basic(conn)
    top_id = conn.execute(
        "SELECT id FROM fillups WHERE vehicle_id = ? AND mileage = 1600",
        (vehicle_id,),
    ).fetchone()[0]
    resp = client.patch(
        f"/api/fillups/{top_id}",
        json={"cost": 42.126, "station": "HEB", "missed_last_fill": True},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["cost"] == 42.13
    assert body["station"] == "HEB"
    assert body["missed_last_fill"] is True
    assert body["mpg"] is None  # missed fill nulls the derivation
    assert body["mileage"] == 1600  # untouched


def test_patch_missing_404(client):
    resp = client.patch("/api/fillups/999", json={"cost": 1.0})
    assert resp.status_code == 404


def test_delete(conn, client):
    vehicle_id = seed_basic(conn)
    middle_id = conn.execute(
        "SELECT id FROM fillups WHERE vehicle_id = ? AND mileage = 1300",
        (vehicle_id,),
    ).fetchone()[0]

    resp = client.delete(f"/api/fillups/{middle_id}")
    assert resp.status_code == 204

    resp = client.delete(f"/api/fillups/{middle_id}")
    assert resp.status_code == 404

    listing = client.get(f"/api/fillups?vehicle_id={vehicle_id}").json()
    assert listing["total"] == 2
    # Derivation now spans the gap left by the deleted row.
    assert listing["items"][0]["mpf"] == 600


def test_context(conn, client):
    vehicle_id = seed_vehicle(conn, tank_size_gal=13.0)
    stations = [
        ("Kroger", "77077"),
        ("Shell", "77007"),
        (None, None),
        ("Costco", "77055"),
        ("Exxon", "77007"),
        ("HEB", "77008"),
        ("7/11", "77477"),
        ("Kroger", "77077"),  # repeat: must dedupe, most recent first
    ]
    for i, (station, zip_code) in enumerate(stations):
        seed_fillup(
            conn,
            vehicle_id,
            1000 + i * 300,
            date=f"2023-01-{i + 1:02d}",
            station=station,
            zip_code=zip_code,
        )

    resp = client.get(f"/api/fillups/context?vehicle_id={vehicle_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["prev_mileage"] == 1000 + 7 * 300
    assert body["last_station"] == "Kroger"
    assert body["last_zip"] == "77077"
    assert body["tank_size_gal"] == 13.0
    # 5 most recent distinct (station, zip) picks, newest first.
    assert body["recent_stations"] == [
        {"station": "Kroger", "zip": "77077"},
        {"station": "7/11", "zip": "77477"},
        {"station": "HEB", "zip": "77008"},
        {"station": "Exxon", "zip": "77007"},
        {"station": "Costco", "zip": "77055"},
    ]


def test_estimated_flags_propagate(conn, client):
    """mileage_estimated is the row's own flag; mpg_estimated is true when
    either endpoint of the MPG interval rests on an estimated odometer."""
    vehicle_id = seed_vehicle(conn)
    seed_fillup(conn, vehicle_id, 1000, date="2023-01-01")
    seed_fillup(
        conn, vehicle_id, 1300, date="2023-01-10",
        mileage_estimated=True, gauge_notches=2.5,
    )
    seed_fillup(conn, vehicle_id, 1600, date="2023-01-20")

    body = client.get(f"/api/fillups?vehicle_id={vehicle_id}").json()
    by_mileage = {item["mileage"]: item for item in body["items"]}
    assert by_mileage[1000]["mileage_estimated"] is False
    assert by_mileage[1000]["mpg_estimated"] is False
    assert by_mileage[1000]["gauge_notches"] is None
    assert by_mileage[1300]["mileage_estimated"] is True
    assert by_mileage[1300]["mpg_estimated"] is True
    assert by_mileage[1300]["gauge_notches"] == 2.5
    # Own odometer real, but the previous (interval start) is estimated.
    assert by_mileage[1600]["mileage_estimated"] is False
    assert by_mileage[1600]["mpg_estimated"] is True

    points = client.get(f"/api/stats/mpg?vehicle_id={vehicle_id}").json()
    assert [p["estimated"] for p in points] == [False, True, True]


def test_context_empty_vehicle(conn, client):
    vehicle_id = seed_vehicle(conn)
    resp = client.get(f"/api/fillups/context?vehicle_id={vehicle_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["prev_mileage"] is None
    assert body["last_station"] is None
    assert body["recent_stations"] == []
