from conftest import seed_fillup, seed_vehicle


def seed_stats(conn):
    vehicle_id = seed_vehicle(conn)
    seed_fillup(conn, vehicle_id, 1000, date="2023-01-05", gallons=10.0, cost=30.0)
    seed_fillup(conn, vehicle_id, 1300, date="2023-01-25", gallons=10.0, cost=40.0)
    seed_fillup(
        conn, vehicle_id, 1600, date="2023-02-10", gallons=12.0, cost=36.0,
        missed_last_fill=True,
    )
    seed_fillup(conn, vehicle_id, 1900, date="2023-02-20", gallons=10.0, cost=25.0)
    return vehicle_id


def test_mpg_points_ascending_with_null_gap(conn, client):
    vehicle_id = seed_stats(conn)
    resp = client.get(f"/api/stats/mpg?vehicle_id={vehicle_id}")
    assert resp.status_code == 200
    points = resp.json()
    assert [p["mileage"] for p in points] == [1000, 1300, 1600, 1900]  # ascending
    assert points[0]["mpg"] is None  # first fill: no previous mileage
    assert points[1]["mpg"] == 30.0
    assert points[2]["mpg"] is None  # missed-fill gap for the chart
    assert points[3]["mpg"] == 30.0
    assert points[1]["date"] == "2023-01-25"


def test_cost_by_month_grouping(conn, client):
    vehicle_id = seed_stats(conn)
    resp = client.get(f"/api/stats/cost-by-month?vehicle_id={vehicle_id}")
    assert resp.status_code == 200
    assert resp.json() == [
        {"month": "2023-01", "cost": 70.0, "gallons": 20.0, "fillups": 2},
        {"month": "2023-02", "cost": 61.0, "gallons": 22.0, "fillups": 2},
    ]


def test_stats_unknown_vehicle_404(client):
    assert client.get("/api/stats/mpg?vehicle_id=999").status_code == 404
    assert client.get("/api/stats/cost-by-month?vehicle_id=999").status_code == 404
