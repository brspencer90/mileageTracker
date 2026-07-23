#!/usr/bin/env python3
"""Seed/refresh the SQLite DB from a legacy mileageTracker CSV export (MT-3).

Usage:
    python scripts/import_csv.py mileageTracker.csv --db data/mileage.db [--dry-run]

Runs migrations first, imports via backend/app/importer.py (idempotent:
re-running skips existing rows), prints the ImportReport, and exits nonzero
if nothing was inserted or skipped.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.db import connect, run_migrations  # noqa: E402
from app.importer import import_fillups, rows_from_legacy_csv  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", help="Path to the legacy CSV export")
    parser.add_argument("--db", default="data/mileage.db", help="SQLite file (default: data/mileage.db)")
    parser.add_argument("--dry-run", action="store_true", help="Parse and report, but roll back all writes")
    args = parser.parse_args()

    if not Path(args.csv_path).is_file():
        print(f"error: CSV file not found: {args.csv_path}", file=sys.stderr)
        return 2

    conn = connect(args.db)
    try:
        run_migrations(conn)
        warnings: list[str] = []
        rows = rows_from_legacy_csv(args.csv_path, warnings=warnings)
        report = import_fillups(conn, rows, dry_run=args.dry_run)
        report.warnings.extend(warnings)
    finally:
        conn.close()

    print(f"ImportReport{' (dry run, rolled back)' if args.dry_run else ''}:")
    print(f"  inserted:         {report.inserted}")
    print(f"  skipped_existing: {report.skipped_existing}")
    print(f"  vehicles_created: {report.vehicles_created}")
    print(f"  warnings:         {len(report.warnings)}")
    for warning in report.warnings:
        print(f"    - {warning}")

    if report.inserted == 0 and report.skipped_existing == 0:
        print("error: nothing imported", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
