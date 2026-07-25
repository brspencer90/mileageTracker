"""One-time migration: copy the v2 SQLite ledger into the SQL Server v2 tables.

Reads the local source-of-truth SQLite DB and writes it into the `vehicles` /
`fillups` tables on the SQL Server named in .env's `sqlss_conn_str` (the legacy
`mileage` table there is left untouched). Idempotency guard: aborts if `fillups`
already has rows, so it can't double-insert.

    backend\\.venv\\Scripts\\python scripts\\migrate_sqlite_to_sqlserver.py --sqlite data/mileage.db
"""
import argparse
import re
import sqlite3
import sys
from pathlib import Path

import pyodbc

REPO = Path(__file__).resolve().parent.parent
DRIVER = "{ODBC Driver 18 for SQL Server}"

FILLUP_COLS = [
    "vehicle_id", "date", "mileage", "gallons", "cost", "station", "zip",
    "missed_last_fill", "mileage_estimated", "gauge_notches", "partial_fill",
]


def conn_str() -> str:
    for line in (REPO / ".env").read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line.startswith("sqlss_conn_str"):
            frag = line.split("=", 1)[1].strip().strip("'").strip('"')
            return f"DRIVER={DRIVER};{frag};TrustServerCertificate=Yes"
    raise SystemExit("sqlss_conn_str not found in .env")


def run_schema(cur):
    sql = (REPO / "backend/app/schema.sql").read_text(encoding="utf-8")
    lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
    for stmt in [s.strip() for s in re.split(r"\n\s*\n", "\n".join(lines)) if s.strip()]:
        cur.execute(stmt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sqlite", required=True)
    args = ap.parse_args()

    s = sqlite3.connect(args.sqlite)
    s.row_factory = sqlite3.Row
    vehicles = s.execute("SELECT * FROM vehicles ORDER BY id").fetchall()
    fillups = s.execute("SELECT * FROM fillups ORDER BY id").fetchall()
    s.close()
    print(f"SQLite source: {len(vehicles)} vehicle(s), {len(fillups)} fill-ups")

    cn = pyodbc.connect(conn_str(), timeout=10, autocommit=False)
    cur = cn.cursor()
    print("target DB:", cur.execute("SELECT DB_NAME()").fetchone()[0])
    run_schema(cur)

    existing = cur.execute("SELECT COUNT(*) FROM fillups").fetchone()[0]
    if existing:
        cn.rollback(); cn.close()
        sys.exit(f"ABORT: fillups already has {existing} rows — refusing to double-migrate.")

    idmap = {}
    for v in vehicles:
        cur.execute(
            "INSERT INTO vehicles (name, make, model, [year], tank_size_gal)"
            " OUTPUT INSERTED.id VALUES (?, ?, ?, ?, ?)",
            v["name"], v["make"], v["model"], v["year"], v["tank_size_gal"],
        )
        idmap[v["id"]] = cur.fetchone()[0]

    placeholders = ", ".join("?" * len(FILLUP_COLS))
    cols = ", ".join(f"[{c}]" if c in ("date", "year") else c for c in FILLUP_COLS)
    for f in fillups:
        cur.execute(
            f"INSERT INTO fillups ({cols}) VALUES ({placeholders})",
            idmap[f["vehicle_id"]], f["date"], f["mileage"], f["gallons"], f["cost"],
            f["station"], f["zip"], f["missed_last_fill"], f["mileage_estimated"],
            f["gauge_notches"], f["partial_fill"],
        )
    cn.commit()

    nv = cur.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0]
    nf = cur.execute("SELECT COUNT(*) FROM fillups").fetchone()[0]
    npend = cur.execute("SELECT COUNT(*) FROM fillups WHERE mileage IS NULL").fetchone()[0]
    npart = cur.execute("SELECT COUNT(*) FROM fillups WHERE partial_fill = 1").fetchone()[0]
    newest = cur.execute("SELECT TOP 1 [date], mileage FROM fillups WHERE mileage IS NOT NULL ORDER BY mileage DESC").fetchone()
    cn.close()
    print(f"MIGRATED -> vehicles: {nv}, fillups: {nf} (pending {npend}, partial {npart}), newest: {newest[0]} @ {newest[1]} mi")


if __name__ == "__main__":
    main()
