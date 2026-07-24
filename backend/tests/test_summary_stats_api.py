"""Tests for GET /api/stats/summary (dashboard tiles).

The fixture is hand-computed. Real fills (mileage order), gallons=10 unless
noted, so mpg = mileage_delta / 10:

    R1  m=1000  mpg None (first fill)         date 2023-01-01
    R2  m=1300  mpg 30                        date 2023-01-20
    R3  m=1600  mpg 30                        date 2023-02-10
    R4  m=1920  mpg 32                        date 2023-03-01
    R5  m=2160  mpg 24                        date 2023-03-20
    R6  m=2400  mpg 24                        date 2023-04-05
    R7  m=2640  mpg 24  cost NULL             date 2023-04-20
    R8  m=2880  mpg 24                        date 2023-05-05
    R9  m=3120  mpg 24                        date 2023-05-30  (31d before latest)
    R10 m=3360  mpg 24                        date 2023-05-31  (exactly 30d: incl.)
    R11 m=3600  mpg 24                        date 2023-06-10
    R12 m=3900  gallons 2 -> mpg 150 OUTLIER  date 2023-06-20
    P   pending (mileage NULL) gallons 8 cost 28  date 2023-06-30 (latest)

In-band (15..40) mpg, mileage order: [30,30,32,24,24,24,24,24,24,24]
  lifetime_mpg = 260/10 = 26.0
  recent_mpg   = last 8 = [32,24,24,24,24,24,24,24] = 200/8 = 25.0
  mpg_delta    = 25.0 - 26.0 = -1.0
Outlier (150) and R1 (None) are excluded from both averages.
"""

from conftest import seed_fillup, seed_vehicle


def _seed_summary(conn):
    v = seed_vehicle(conn)
    seed_fillup(conn, v, 1000, date="2023-01-01", gallons=10, cost=40)
    seed_fillup(conn, v, 1300, date="2023-01-20", gallons=10, cost=40)
    seed_fillup(conn, v, 1600, date="2023-02-10", gallons=10, cost=40)
    seed_fillup(conn, v, 1920, date="2023-03-01", gallons=10, cost=40)
    seed_fillup(conn, v, 2160, date="2023-03-20", gallons=10, cost=40)
    seed_fillup(conn, v, 2400, date="2023-04-05", gallons=10, cost=40)
    seed_fillup(conn, v, 2640, date="2023-04-20", gallons=10, cost=None)  # NULL cost
    seed_fillup(conn, v, 2880, date="2023-05-05", gallons=10, cost=40)
    seed_fillup(conn, v, 3120, date="2023-05-30", gallons=10, cost=40)
    seed_fillup(conn, v, 3360, date="2023-05-31", gallons=10, cost=40)
    seed_fillup(conn, v, 3600, date="2023-06-10", gallons=10, cost=40)
    seed_fillup(conn, v, 3900, date="2023-06-20", gallons=2, cost=40)  # partial outlier
    seed_fillup(conn, v, None, date="2023-06-30", gallons=8, cost=28)  # pending
    return v


def test_summary_all_fields(conn, client):
    v = _seed_summary(conn)
    resp = client.get(f"/api/stats/summary?vehicle_id={v}")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "odometer": 3900,          # MAX(mileage); pending NULL ignored
        "total_fills": 13,         # 12 real + 1 pending
        "tracked_since": "2023-01-01",
        "lifetime_mpg": 26.0,      # outlier (150) & first-fill None excluded
        "recent_mpg": 25.0,        # most recent 8 in-band
        "mpg_delta": -1.0,
        # last 10 real fills = R3..R12; window[1:]=R4..R12, R7 cost NULL skipped
        # -> 8*40=320 over (3900-1600)=2300 -> 0.139
        "cost_per_mile": 0.139,
        # date >= 2023-05-31: R10,R11,R12,P -> 40+40+40+28 = 148.0
        "spend_30d": 148.0,
        "spend_30d_fills": 4,
        # recent 12 by date = R2..R12,P; (2023-06-30 - 2023-01-20)=161d / 11 = 14.6
        "avg_days_between": 14.6,
    }


def test_summary_30day_boundary_is_inclusive(conn, client):
    """R10 is exactly 30 days before the latest fill and must be counted;
    R9 (31 days) must not be."""
    v = _seed_summary(conn)
    body = client.get(f"/api/stats/summary?vehicle_id={v}").json()
    assert body["spend_30d_fills"] == 4  # R10 included, R9 excluded


def test_summary_pending_row_counts_for_spend_not_mpg(conn, client):
    """The pending (mileage NULL) row contributes cost/date to spend_30d and
    total_fills, but never to the MPG averages or odometer."""
    v = seed_vehicle(conn)
    seed_fillup(conn, v, 1000, date="2026-06-01", gallons=10, cost=30)
    seed_fillup(conn, v, 1250, date="2026-06-11", gallons=10, cost=32)  # mpg 25
    seed_fillup(conn, v, None, date="2026-06-20", gallons=9, cost=27)   # pending
    body = client.get(f"/api/stats/summary?vehicle_id={v}").json()
    assert body["total_fills"] == 3
    assert body["odometer"] == 1250            # pending NULL ignored
    assert body["lifetime_mpg"] == 25.0        # single derived mpg, pending absent
    assert body["spend_30d"] == 89.0           # 30 + 32 + 27
    assert body["spend_30d_fills"] == 3


def test_summary_empty_vehicle_returns_nones(conn, client):
    v = seed_vehicle(conn)
    resp = client.get(f"/api/stats/summary?vehicle_id={v}")
    assert resp.status_code == 200
    assert resp.json() == {
        "odometer": None,
        "total_fills": 0,
        "tracked_since": None,
        "lifetime_mpg": None,
        "recent_mpg": None,
        "mpg_delta": None,
        "cost_per_mile": None,
        "spend_30d": None,
        "spend_30d_fills": 0,
        "avg_days_between": None,
    }


def test_summary_single_fill(conn, client):
    """One fill: no derived MPG, no interval for cost/mile or day-gaps."""
    v = seed_vehicle(conn)
    seed_fillup(conn, v, 5000, date="2025-01-01", gallons=10, cost=35)
    body = client.get(f"/api/stats/summary?vehicle_id={v}").json()
    assert body["odometer"] == 5000
    assert body["total_fills"] == 1
    assert body["lifetime_mpg"] is None
    assert body["recent_mpg"] is None
    assert body["mpg_delta"] is None
    assert body["cost_per_mile"] is None
    assert body["avg_days_between"] is None
    assert body["spend_30d"] == 35.0
    assert body["spend_30d_fills"] == 1


def test_summary_unknown_vehicle_404(client):
    assert client.get("/api/stats/summary?vehicle_id=999").status_code == 404
