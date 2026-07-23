from datetime import datetime
from pathlib import Path

from openpyxl import Workbook

from app import queries
from app.importer import import_fillups, rows_from_legacy_csv, rows_from_xlsx

SAMPLE = Path(__file__).parent / "fixtures" / "sample.csv"

FIXTURE_ROWS = 5


def test_normalization():
    rows = list(rows_from_legacy_csv(SAMPLE))
    assert len(rows) == FIXTURE_ROWS

    # BOM stripped from the first header; '#N/A' and blank -> None; date -> ISO.
    assert rows[0] == {
        "vehicle_name": "TestCar",
        "date": "2019-05-10",
        "mileage": 334,
        "gallons": 11.571,
        "cost": 29.61,
        "station": None,
        "zip": None,
        "missed_last_fill": True,
    }
    assert rows[1]["zip"] == "77077"  # float-formatted '77077.0'
    assert rows[1]["missed_last_fill"] is False
    assert rows[2]["zip"] == "07007"  # short zip left-padded to 5
    assert rows[3]["station"] is None
    assert rows[3]["zip"] is None
    assert rows[4]["missed_last_fill"] is True


def test_import_creates_vehicle_and_derives_mpg(conn):
    warnings: list[str] = []
    report = import_fillups(conn, rows_from_legacy_csv(SAMPLE, warnings=warnings))

    assert report.inserted == FIXTURE_ROWS
    assert report.skipped_existing == 0
    assert report.vehicles_created == 1
    # Fixture stored-MPG values follow the legacy prev-gallons formula, so the
    # cross-check must not fire.
    assert warnings == []

    vehicle_id = conn.execute(
        "SELECT id FROM vehicles WHERE name = 'TestCar'"
    ).fetchone()[0]
    points = queries.mpg_points(conn, vehicle_id)
    # Derived at read time with the *current* row's gallons; missed fills null.
    assert [p["mpg"] for p in points] == [None, 26.24, 23.13, 25.12, None]


def test_import_is_idempotent(conn):
    first = import_fillups(conn, rows_from_legacy_csv(SAMPLE))
    assert first.inserted == FIXTURE_ROWS

    second = import_fillups(conn, rows_from_legacy_csv(SAMPLE))
    assert second.inserted == 0
    assert second.skipped_existing == FIXTURE_ROWS
    assert second.vehicles_created == 0

    total = conn.execute("SELECT COUNT(*) FROM fillups").fetchone()[0]
    assert total == FIXTURE_ROWS


def test_dry_run_rolls_back(conn):
    report = import_fillups(conn, rows_from_legacy_csv(SAMPLE), dry_run=True)
    assert report.inserted == FIXTURE_ROWS
    assert conn.execute("SELECT COUNT(*) FROM fillups").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0] == 0


def test_mpg_crosscheck_warns_on_divergence(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text(
        "Car,Date,Mileage,Gallons,Cost,Gas Station,Zip code,Missed Last Fill,MPF,MPG\n"
        "TestCar,05/10/2019,334,11.571,29.61,,#N/A,1,#N/A,#N/A\n"
        "TestCar,05/20/2019,627,11.168,28.58,Kroger,77077,0,293,99.99\n",
        encoding="utf-8-sig",
    )
    warnings: list[str] = []
    rows = list(rows_from_legacy_csv(path, warnings=warnings))
    assert len(rows) == 2
    assert len(warnings) == 1
    assert "line 3" in warnings[0]


def test_blank_cost_imported_as_null_with_warning(conn, tmp_path):
    path = tmp_path / "blank_cost.csv"
    path.write_text(
        "Car,Date,Mileage,Gallons,Cost,Gas Station,Zip code,Missed Last Fill,MPF,MPG\n"
        "TestCar,03/30/2023,33088,11.734,,,#N/A,0,333,30.15\n",
        encoding="utf-8-sig",
    )
    warnings: list[str] = []
    rows = list(rows_from_legacy_csv(path, warnings=warnings))
    assert len(rows) == 1
    assert rows[0]["cost"] is None
    assert len(warnings) == 1
    assert "missing cost" in warnings[0]

    report = import_fillups(conn, rows)
    assert report.inserted == 1
    assert conn.execute("SELECT cost FROM fillups").fetchone()[0] is None


def test_unparseable_row_skipped_with_warning(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text(
        "Car,Date,Mileage,Gallons,Cost,Gas Station,Zip code,Missed Last Fill,MPF,MPG\n"
        "TestCar,not-a-date,627,11.168,28.58,Kroger,77077,0,#N/A,#N/A\n"
        "TestCar,05/20/2019,900,11.168,28.58,Kroger,77077,1,#N/A,#N/A\n",
        encoding="utf-8-sig",
    )
    warnings: list[str] = []
    rows = list(rows_from_legacy_csv(path, warnings=warnings))
    assert len(rows) == 1
    assert rows[0]["mileage"] == 900
    assert len(warnings) == 1
    assert "line 2" in warnings[0]


# --- xlsx adapter (MT-20 / MT-21) -------------------------------------------


def _build_xlsx(path: Path, rows: list[tuple]) -> None:
    """Write a fixture mimicking MileageTracker.xlsx: header row 1, unnamed
    gauge column H, junk columns J/K (ignored by the adapter)."""
    wb = Workbook()
    ws = wb.active
    ws.append(
        ("Car", "Date", "Mileage", "Gallons", "Cost", "Gas Station",
         "Zip", None, "Missed Last Fill", "junk J", "junk K")
    )
    for row in rows:
        ws.append(row + ("jj", "jk"))
    wb.save(path)


def _xlsx_fixture(tmp_path: Path) -> Path:
    path = tmp_path / "fixture.xlsx"
    _build_xlsx(path, [
        # car, date, mileage, gallons, cost, station, zip(int), gauge, missed
        ("Tiger", datetime(2023, 1, 1), 1000, 10.0, 30.0, "Kroger", 77077, None, 1),
        (None, datetime(2023, 1, 10), 1300, 10.0, 30.0, "Shell", 77007, None, 0),
        (None, datetime(2023, 1, 15), None, None, None, None, None, None, None),  # placeholder
        (None, datetime(2023, 1, 20), 1600, 10.0, None, None, None, 2.5, None),   # blank cost
        (None, datetime(2023, 9, 1), 5000, 10.0, 30.0, None, None, None, None),   # >180-day gap
        (None, datetime(2023, 9, 10), None, 10.0, 30.0, None, None, None, None),  # single blank run
        (None, datetime(2023, 9, 20), 6000, 10.0, 30.0, None, None, None, None),  # closing anchor
        (None, datetime(2024, 1, 1), 68186, 11.0, 40.0, None, None, None, None),  # opening anchor
        (None, datetime(2024, 1, 5), None, 10.753, 43.0, "Costco", 77007, None, None),  # blank pair 1
        (None, datetime(2024, 1, 10), None, 9.212, 33.15, "Costco", 77479, None, None),  # blank pair 2
        (None, datetime(2024, 1, 15), 69038, 11.304, 40.0, None, None, None, None),  # closing anchor
        (None, datetime(2024, 1, 20), None, 9.0, 30.0, None, None, None, None),   # trailing: unbracketed
    ])
    return path


def test_xlsx_normalization_and_policy(tmp_path):
    warnings: list[str] = []
    stats: dict[str, int] = {}
    rows = rows_from_xlsx(_xlsx_fixture(tmp_path), warnings=warnings, stats=stats)

    # 12 data rows - 1 placeholder - 1 unbracketed blank-mileage row.
    assert len(rows) == 10
    assert stats["skipped_placeholder"] == 1
    assert any("row 4" in w and "placeholder" in w for w in warnings)
    assert any("row 13" in w and "blank mileage" in w for w in warnings)

    first = rows[0]
    assert first["vehicle_name"] == "Tiger"
    assert first["date"] == "2023-01-01"
    assert first["zip"] == "77077"  # int-typed cell -> 5-char string
    assert first["missed_last_fill"] is True
    assert first["gauge_notches"] is None
    assert first["mileage_estimated"] is False

    # Blank Car defaults to the last seen name.
    assert rows[1]["vehicle_name"] == "Tiger"
    assert rows[1]["zip"] == "77007"

    # Blank cost -> NULL with warning; gauge column imports raw; blank missed -> 0.
    blank_cost = rows[2]
    assert blank_cost["mileage"] == 1600
    assert blank_cost["cost"] is None
    assert blank_cost["gauge_notches"] == 2.5
    assert blank_cost["missed_last_fill"] is False
    assert any("row 5" in w and "missing cost" in w for w in warnings)

    # >180-day gap forces the missed flag even though the source left it blank.
    gap_row = rows[3]
    assert gap_row["mileage"] == 5000
    assert gap_row["missed_last_fill"] is True
    assert any("row 6" in w and "forced missed_last_fill" in w for w in warnings)


def test_xlsx_mileage_reconstruction(tmp_path):
    warnings: list[str] = []
    rows = rows_from_xlsx(_xlsx_fixture(tmp_path), warnings=warnings)
    by_date = {r["date"]: r for r in rows}

    # Single blank run: 5000 -> 6000, weights (10, 10) -> midpoint.
    single = by_date["2023-09-10"]
    assert single["mileage"] == 5500
    assert single["mileage_estimated"] is True

    # Consecutive pair, the MT-21 reference bracket: 68186 -> 69038 with
    # gallons weights (10.753, 9.212, 11.304) -> exactly 68479 and 68730.
    assert by_date["2024-01-05"]["mileage"] == 68479
    assert by_date["2024-01-05"]["mileage_estimated"] is True
    assert by_date["2024-01-10"]["mileage"] == 68730
    assert by_date["2024-01-10"]["mileage_estimated"] is True
    assert by_date["2024-01-15"]["mileage_estimated"] is False

    assert any("estimated mileage 68479" in w for w in warnings)
    assert any("estimated mileage 68730" in w for w in warnings)


def test_xlsx_import_and_idempotency(conn, tmp_path):
    path = _xlsx_fixture(tmp_path)
    stats: dict[str, int] = {}
    report = import_fillups(conn, rows_from_xlsx(path, stats=stats))
    assert report.inserted == 10
    assert report.estimated == 3  # one single run + one consecutive pair
    assert report.vehicles_created == 1
    assert stats["skipped_placeholder"] == 1

    row = conn.execute(
        "SELECT mileage_estimated, gauge_notches FROM fillups WHERE mileage = 1600"
    ).fetchone()
    assert row["mileage_estimated"] == 0
    assert row["gauge_notches"] == 2.5
    est = conn.execute(
        "SELECT mileage FROM fillups WHERE mileage_estimated = 1 ORDER BY mileage"
    ).fetchall()
    assert [r["mileage"] for r in est] == [5500, 68479, 68730]

    second = import_fillups(conn, rows_from_xlsx(path))
    assert second.inserted == 0
    assert second.estimated == 0
    assert second.skipped_existing == 10
