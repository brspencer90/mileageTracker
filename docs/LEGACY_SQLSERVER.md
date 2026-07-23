# Legacy SQL Server — source of record & reconciliation

The original Streamlit app (now in `legacy/`) wrote fill-ups to a Microsoft SQL
Server database on the home LAN, **not** to the CSV/xlsx directly. That server is
the authoritative record for the pre-October-2024 era and must be reconciled
against `MileageTracker.xlsx` before `legacy/` is deleted. This file preserves the
access path so the connection survives even after the legacy code is removed.

## Connection metadata (non-secret)

| Field | Value |
|---|---|
| Host / port | `192.168.0.20 : 1433` (SQL Server default port; on the home LAN — the NAS) |
| Database | `mileageTracker` |
| Account | `SA` |
| Driver | `ODBC Driver 18 for SQL Server` (`TrustServerCertificate=Yes`) |
| Password | **In `.env` only** (key `sqlss_conn_str`). `.env` is gitignored — never commit it. |

The connection string lives at repo-root `.env` as `sqlss_conn_str`. pyodbc + the
ODBC driver are installed in the legacy venv `.env_mileage` (the v2 backend venv
deliberately has neither — v2 has no live dependency on this server).

Table `mileage` columns: `car, date, mileage, volume, cost, station, zipCode,
missedLastFill, mpf, mpg` (137 rows as of the reconciliation below). Note `volume`
is what v2 calls `gallons`, and stored `mpf`/`mpg` are ignored (v2 derives them).

## Reconciliation

Read-only diff of the `mileage` table against the xlsx ledger, keyed on mileage.
Script: `scratchpad/reconcile_sqlserver.py` (run with the `.env_mileage` venv, which
also needs `openpyxl`). Writes nothing to either source.

### Findings — 2026-07-19

- **SQL Server: 137 rows. xlsx: 174 data rows (169 with mileage).** 104 mileage keys shared.
- **33 fills are in the SQL Server but absent from the xlsx** — a contiguous block from
  2023-11-25 (mileage 38,846) through 2024-09-19 (48,442). This is the same stretch the
  xlsx showed as a 10-month "unrecorded gap": it was never unrecorded — those fills were
  logged in the old app and simply never copied into the spreadsheet. **Recoverable data.**
- **The 2023-10-05 fill** the xlsx carries with an estimated odometer (37,399) has its real
  value in the DB: **37,400** — the interpolation estimator was off by a single mile
  (strong validation of the MT-21 method).
- **65 fills are in the xlsx but not the SQL Server** — everything from 2024-10-07 onward,
  logged after the old app was retired. Expected, not lost.
- **2 field mismatches** at mileage 28,685 / 28,710 (2022-11-24): the SQL Server still holds
  the original mislog (0.969 gal at 28,685 → the 330-MPG artifact); the xlsx holds Bryan's
  correction. Here the **xlsx is the more-correct source** — do not copy these two back.

**Net:** the xlsx is authoritative from Oct 2024 on and for the two corrected 2022 rows;
the SQL Server is authoritative for the ~32 fills in the Nov 2023–Sep 2024 gap. A complete
ledger is the union, minus the two known-bad 2022 rows.

### Merge applied — 2026-07-19 (MT-25 done)

`scripts/backfill_sqlserver.py` merged the SQL Server rows into `data/mileage.db`:
**32 gap fills inserted**, 104 already-present rows skipped, the two known-bad 2022 rows
auto-skipped (xlsx values kept). Two corrections applied: the 2023-10-05 estimate (37,399)
replaced with the DB's real 37,400 (`mileage_estimated` cleared), and the now-obsolete
forced `missed_last_fill` on the 2024-09-08 / 48,137 row cleared (its gap is filled).
Result: **204 rows, monotonic, no MPG anomalies except the still-open Feb 2023 pair.**

**The SQLite DB is now the single source of truth.** The SQL Server can be retired; this doc
plus the backfill script remain the record of how it was reached. Do not re-import the xlsx
over the DB. Backups: `scripts/export_backup.py` → `data/backups/*.csv`.
