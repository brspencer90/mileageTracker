"""One-time MT-25 backfill: merge the legacy SQL Server ledger into SQLite.

The old Streamlit app logged to a SQL Server DB (see docs/LEGACY_SQLSERVER.md).
The 2026-07-19 reconciliation found ~32 real fills there — the Nov 2023 to
Sep 2024 stretch — that never made it into MileageTracker.xlsx, so they are
absent from the SQLite DB. This script pulls the SQL Server `mileage` table and
inserts the missing fills into SQLite via the shared importer sink, then applies
two data corrections the reconciliation identified.

Run with the LEGACY venv (it has pyodbc + the ODBC driver; the backend venv
deliberately has neither):

    .env_mileage\\Scripts\\python scripts\\backfill_sqlserver.py --db data/mileage.db

Read-only against SQL Server (SELECT only). Idempotent against SQLite: inserts
use INSERT OR IGNORE, and the corrections are no-ops once applied.
"""
import argparse
import sys
from pathlib import Path

import pyodbc

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
from app.importer import import_fillups, _norm_zip  # noqa: E402

DRIVER = "{ODBC Driver 18 for SQL Server}"

# The 2023-10-05 fill is already in SQLite as an interpolation ESTIMATE
# (mileage 37399, mileage_estimated=1). SQL Server holds its real odometer,
# 37400. We must not insert 37400 as a second row for the same physical fill;
# instead we update the estimate in place (see apply_corrections).
ESTIMATE_REAL_MILEAGE = 37400

# The two 2022-11-24 rows are a known swap: the xlsx (already in SQLite) holds
# Bryan's correction; SQL Server still holds the original mislog. INSERT OR
# IGNORE skips them (mileage keys 28685/28710 already present), so the correct
# xlsx values win automatically — listed here only for the audit log.
KNOWN_BAD_SQL_MILEAGES = {28685, 28710}


def load_conn_str() -> str:
    for line in (REPO / ".env").read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line.startswith("sqlss_conn_str"):
            return line.split("=", 1)[1].strip().strip("'").strip('"')
    raise SystemExit("sqlss_conn_str not found in .env")


def sql_rows(conn_str: str) -> list[dict]:
    cnxn = pyodbc.connect(
        f"DRIVER={DRIVER};{conn_str};TrustServerCertificate=Yes", timeout=8
    )
    cur = cnxn.cursor()
    cur.execute("SELECT car, date, mileage, volume, cost, station, zipCode,"
                " missedLastFill FROM mileage")
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cnxn.close()
    return rows


def to_normalized(r: dict) -> dict:
    d = r["date"]
    iso = d.date().isoformat() if hasattr(d, "date") else str(d)[:10]
    return {
        "vehicle_name": (r["car"] or "Tiger").strip(),
        "date": iso,
        "mileage": int(r["mileage"]),
        "gallons": float(r["volume"]),
        "cost": float(r["cost"]) if r["cost"] is not None else None,
        "station": (r["station"].strip() or None) if r["station"] else None,
        "zip": _norm_zip(str(r["zipCode"]).removesuffix(".0")) if r["zipCode"] is not None else None,
        "missed_last_fill": bool(int(r["missedLastFill"] or 0)),
        "mileage_estimated": False,
        "gauge_notches": None,
    }


def apply_corrections(conn) -> list[str]:
    log = []
    # Correction 1: replace the 2023-10-05 estimate with SQL Server's real value.
    cur = conn.execute(
        "UPDATE fillups SET mileage = ?, mileage_estimated = 0"
        " WHERE date = '2023-10-05' AND mileage_estimated = 1",
        (ESTIMATE_REAL_MILEAGE,),
    )
    if cur.rowcount:
        log.append(f"2023-10-05: estimate replaced with real odometer {ESTIMATE_REAL_MILEAGE}"
                   " (mileage_estimated cleared)")
    # Correction 2: the post-gap row's forced missed_last_fill flag is now
    # obsolete — the gap it spanned is filled by the backfilled rows.
    cur = conn.execute(
        "UPDATE fillups SET missed_last_fill = 0"
        " WHERE date = '2024-09-08' AND mileage = 48137 AND missed_last_fill = 1"
    )
    if cur.rowcount:
        log.append("2024-09-08 (48137): cleared obsolete forced missed_last_fill"
                   " (gap now filled by backfilled fills)")
    conn.commit()
    return log


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn_str = load_conn_str()
    print("Reading SQL Server (read-only)...", flush=True)
    raw = sql_rows(conn_str)
    print(f"  {len(raw)} rows in SQL Server `mileage`")

    # Feed everything except the estimate-duplicate mileage; INSERT OR IGNORE
    # skips the ~103 already-present rows and inserts only the genuine gap fills.
    rows = [to_normalized(r) for r in raw if int(r["mileage"]) != ESTIMATE_REAL_MILEAGE]

    import sqlite3
    conn = sqlite3.connect(args.db)
    conn.execute("PRAGMA foreign_keys=ON")
    report = import_fillups(conn, rows, dry_run=args.dry_run)
    print("\nImportReport:")
    print(f"  inserted:         {report.inserted}")
    print(f"  skipped_existing: {report.skipped_existing}")
    print(f"  known-bad SQL rows auto-skipped (kept xlsx values): "
          f"{sorted(KNOWN_BAD_SQL_MILEAGES)}")

    if not args.dry_run:
        for line in apply_corrections(conn):
            print(f"  correction: {line}")
    conn.close()
    print("\nDone." + (" (dry run — rolled back)" if args.dry_run else ""))


if __name__ == "__main__":
    main()
