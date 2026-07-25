"""MT-9: partial-fill-aware MPG derivation and the suggest-partial detector."""

from app import queries
from conftest import seed_fillup, seed_vehicle


def _by_mileage(conn, vid):
    """Derived rows keyed by mileage for easy assertions."""
    rows = queries._derive(queries._real_rows(conn, vid))
    return {r["mileage"]: r for r in rows}


def test_full_only_unchanged(conn):
    """No partials: MPG = span / this fill's gallons (standard method)."""
    vid = seed_vehicle(conn)
    seed_fillup(conn, vid, 1000, gallons=10.0)  # first: no anchor -> None
    seed_fillup(conn, vid, 1300, gallons=10.0)  # 300 / 10
    seed_fillup(conn, vid, 1600, gallons=12.0)  # 300 / 12
    d = _by_mileage(conn, vid)
    assert d[1000]["mpg"] is None
    assert d[1300]["mpg"] == 30.0 and d[1300]["mpf"] == 300
    assert d[1600]["mpg"] == 25.0


def test_partial_rolls_into_next_full(conn):
    """A partial gets no MPG; its gallons join the next full fill's window."""
    vid = seed_vehicle(conn)
    seed_fillup(conn, vid, 1000, gallons=10.0)                     # anchor
    seed_fillup(conn, vid, 1100, gallons=3.0, partial_fill=True)   # partial: None
    seed_fillup(conn, vid, 1300, gallons=8.0)                      # full: 300 / (3+8)
    d = _by_mileage(conn, vid)
    assert d[1100]["mpg"] is None and d[1100]["mpf"] is None
    assert d[1300]["mpf"] == 300
    assert d[1300]["mpg"] == round(300 / 11.0, 2)  # 27.27


def test_consecutive_partials(conn):
    """Several partials in a row all fold into the closing full fill."""
    vid = seed_vehicle(conn)
    seed_fillup(conn, vid, 1000, gallons=10.0)
    seed_fillup(conn, vid, 1080, gallons=2.0, partial_fill=True)
    seed_fillup(conn, vid, 1160, gallons=2.5, partial_fill=True)
    seed_fillup(conn, vid, 1360, gallons=6.0)  # 360 / (2+2.5+6)
    d = _by_mileage(conn, vid)
    assert d[1080]["mpg"] is None and d[1160]["mpg"] is None
    assert d[1360]["mpg"] == round(360 / 10.5, 2)  # 34.29


def test_missed_fill_corrupts_window_then_reanchors(conn):
    """A missed fill nulls the fill it lands on, which re-anchors a clean window."""
    vid = seed_vehicle(conn)
    seed_fillup(conn, vid, 1000, gallons=10.0)
    seed_fillup(conn, vid, 1300, gallons=10.0)                       # 30.0
    seed_fillup(conn, vid, 2000, gallons=10.0, missed_last_fill=True)  # gap -> None
    seed_fillup(conn, vid, 2300, gallons=10.0)                       # 30.0 (fresh anchor)
    d = _by_mileage(conn, vid)
    assert d[1300]["mpg"] == 30.0
    assert d[2000]["mpg"] is None  # unknown miles/gallons across the gap
    assert d[2300]["mpg"] == 30.0


def test_estimated_propagates(conn):
    """mpg_estimated when this fill's or the anchor's mileage is estimated."""
    vid = seed_vehicle(conn)
    seed_fillup(conn, vid, 1000, gallons=10.0, mileage_estimated=True)  # anchor est.
    seed_fillup(conn, vid, 1300, gallons=10.0)                          # rests on est. anchor
    seed_fillup(conn, vid, 1600, gallons=10.0)                          # clean
    d = _by_mileage(conn, vid)
    assert d[1300]["mpg_estimated"] is True
    assert d[1600]["mpg_estimated"] is False


def test_leading_and_trailing_partials_are_null(conn):
    vid = seed_vehicle(conn)
    seed_fillup(conn, vid, 1000, gallons=3.0, partial_fill=True)  # leading: None
    seed_fillup(conn, vid, 1200, gallons=10.0)                    # first full: no anchor -> None
    seed_fillup(conn, vid, 1500, gallons=10.0)                    # 30.0
    seed_fillup(conn, vid, 1600, gallons=3.0, partial_fill=True)  # trailing: None
    d = _by_mileage(conn, vid)
    assert d[1000]["mpg"] is None
    assert d[1200]["mpg"] is None
    assert d[1500]["mpg"] == 30.0
    assert d[1600]["mpg"] is None


def test_suggested_partial_fires_on_high_mpg(conn):
    """A full fill deriving to an absurd MPG is flagged as a candidate partial."""
    vid = seed_vehicle(conn)
    seed_fillup(conn, vid, 1000, gallons=10.0)
    seed_fillup(conn, vid, 1500, gallons=10.0)  # 500/10 = 50 MPG -> candidate
    seed_fillup(conn, vid, 1800, gallons=10.0)  # 300/10 = 30 MPG -> normal
    d = _by_mileage(conn, vid)
    assert d[1500]["mpg"] == 50.0
    assert d[1500]["suggested_partial"] is True
    # normal fills are not candidates
    assert d[1800]["mpg"] == 30.0
    assert d[1800]["suggested_partial"] is False


def test_suggested_partial_not_on_flagged_or_normal(conn):
    vid = seed_vehicle(conn)
    seed_fillup(conn, vid, 1000, gallons=10.0)
    seed_fillup(conn, vid, 1300, gallons=10.0)  # 30 MPG, normal
    # an already-flagged tiny partial must not be re-suggested
    seed_fillup(conn, vid, 1330, gallons=1.0, partial_fill=True)
    seed_fillup(conn, vid, 1600, gallons=10.0)
    d = _by_mileage(conn, vid)
    assert d[1300]["suggested_partial"] is False
    assert d[1330]["suggested_partial"] is False  # already partial


def test_flagging_partial_normalizes_neighbors(client, conn):
    """End-to-end: a real partial shows as high-MPG at itself and low at the
    next fill; flagging it nulls its MPG and normalizes the next fill's."""
    vid = seed_vehicle(conn)
    seed_fillup(conn, vid, 1000, gallons=10.0)      # anchor
    a = seed_fillup(conn, vid, 1275, gallons=1.0)   # 275/1 = 275 MPG artifact (a top-up)
    seed_fillup(conn, vid, 1300, gallons=10.0)      # 25/10 = 2.5 MPG artifact

    # before: both neighbors are absurd, and the top-up is a suggested partial
    before = {i["mileage"]: i for i in client.get(f"/api/fillups?vehicle_id={vid}").json()["items"]}
    assert before[1275]["mpg"] == 275.0 and before[1275]["suggested_partial"] is True
    assert before[1300]["mpg"] == 2.5

    r = client.patch(f"/api/fillups/{a}", json={"partial_fill": True})
    assert r.status_code == 200 and r.json()["mpg"] is None

    after = {i["mileage"]: i for i in client.get(f"/api/fillups?vehicle_id={vid}").json()["items"]}
    assert after[1275]["mpg"] is None and after[1275]["suggested_partial"] is False
    assert after[1300]["mpf"] == 300
    assert after[1300]["mpg"] == round(300 / 11.0, 2)  # 27.27 — normalized
