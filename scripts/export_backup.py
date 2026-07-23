"""Export the SQLite fill-up ledger to a timestamped CSV backup.

The SQLite DB is the single source of truth (post MT-25 backfill). This writes a
flat CSV snapshot to data/backups/ so there is always a human-readable, portable
copy of the record of truth. Run it after notable changes, or on a schedule.

    backend\\.venv\\Scripts\\python scripts\\export_backup.py --db data/mileage.db
"""
import argparse
import csv
import sqlite3
from datetime import datetime
from pathlib import Path

FIELDS = ["id", "vehicle_name", "date", "mileage", "mileage_estimated",
          "gallons", "cost", "station", "zip", "missed_last_fill",
          "gauge_notches", "created_at"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--out-dir", default=None,
                    help="default: <db parent>/backups")
    args = ap.parse_args()

    db = Path(args.db)
    out_dir = Path(args.out_dir) if args.out_dir else db.parent / "backups"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = out_dir / f"mileage_backup_{stamp}.csv"

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT f.id, v.name AS vehicle_name, f.date, f.mileage,"
        " f.mileage_estimated, f.gallons, f.cost, f.station, f.zip,"
        " f.missed_last_fill, f.gauge_notches, f.created_at"
        " FROM fillups f JOIN vehicles v ON v.id = f.vehicle_id"
        " ORDER BY v.name, f.mileage"
    ).fetchall()
    conn.close()

    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r[k] for k in FIELDS})

    print(f"Wrote {len(rows)} rows -> {out}")


if __name__ == "__main__":
    main()
