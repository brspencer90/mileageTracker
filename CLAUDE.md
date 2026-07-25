# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

"Mileage tracker v2" — a self-hosted fuel/fill-up tracker (single user, multi-vehicle-ready). FastAPI + SQLite backend serving a Vite + React + TypeScript PWA, designed for sub-30-second fill-up logging from a phone. Target deployment is a Synology DS220+ via **Docker + CI/CD** (build-and-pull: GitHub Actions → GHCR → Watchtower auto-pulls on the NAS), reached from the phone via Tailscale. Local development runs everything on the dev machine.

Product backlog and decisions: `docs/PRODUCT_PLAN.md`. Build plan: `docs/IMPLEMENTATION_PLAN.md`. **NAS/Docker deployment: `docs/DEPLOY_SYNOLOGY.md`** (Dockerfile + docker-compose.yml at repo root; `.github/workflows/` ci.yml + deploy.yml). The SQLite DB is NOT baked into the image — it lives on a `/data` volume so it survives auto-updates; personal data (`*.xlsx`/`*.csv`/`*.db`) is kept out of the image via `.dockerignore`. `/api/version` and the UI's `ver.` footer report the running image's `GIT_SHA`. (The earlier "no Docker, SynoCommunity Python + Task Scheduler" plan was reversed in favor of this CI/CD pipeline.)

## Commands

Backend (from `backend/`, venv at `backend/.venv`):

```
.venv\Scripts\pytest                          # run tests
.venv\Scripts\uvicorn app.main:app --reload   # dev server on :8000 (serves API + built frontend)
```

Frontend (from `frontend/`):

```
npm run dev        # Vite dev server on :5173, proxies /api -> 127.0.0.1:8000
npm run build      # tsc + production build + PWA artifacts into dist/
npx tsc -b --force # typecheck only
npm run icons      # regenerate PWA icons (scripts/generate-icons.mjs, uses sharp)
```

Quick manual start (double-click or run from anywhere): `scripts\start_server.bat` — serves API + built frontend on 127.0.0.1:8000.

Seed/import data (from repo root — the xlsx is the authoritative source; the CSV importer remains for reference):

```
backend\.venv\Scripts\python scripts\import_xlsx.py MileageTracker.xlsx --db data/mileage.db [--dry-run]
```

Run a single test: `.venv\Scripts\pytest tests/test_importer.py -k idempotent`.

## Architecture

- `backend/app/` — FastAPI app. `db.py` opens per-request SQLite connections (WAL, foreign keys, busy_timeout) and runs the migration runner (`PRAGMA user_version` + numbered files in `migrations/`) at startup. `queries.py` holds all SQL, centered on a LAG() window CTE that **derives MPG/MPF at read time** — they are never stored, so edits/deletes/imports can't corrupt neighboring rows. Routers: `vehicles`, `fillups` (CRUD + `/api/fillups/context`, the one-call endpoint powering the form's live MPG preview and station quick-picks), `stats` (chart series). `main.py` also serves `frontend/dist` with an SPA fallback when it exists.
- `backend/app/importer.py` — reusable ingestion: source adapters yield `NormalizedRow` dicts into `import_fillups()`, idempotent via `UNIQUE(vehicle_id, mileage)` + INSERT OR IGNORE. The future SQL Server history migration should be a second adapter feeding the same sink.
- `frontend/src/` — `App.tsx` holds vehicle selection + a two-tab layout (Log/History, no router). `QuickLogForm.tsx` is the product centerpiece. `api/types.ts` must mirror `backend/app/models.py` exactly — there is no codegen; update both together. Charts are Recharts, styled per the dataviz skill; dark/light theming via `lib/theme.ts` matchMedia hook because SVG attrs can't take CSS vars.
- `legacy/` — the old Streamlit + SQL Server app, kept only as reference for the pending SQL Server history migration; delete after that lands. Do not fix bugs there.

## Data semantics & gotchas

- MPG formula is `(mileage - prev_mileage) / current_gallons` (standard full-tank method). The historical CSV used the *previous* row's gallons, so recomputed historical MPG differs from the CSV's stored values by ~0.5–1.5. Stored MPF/MPG columns in the CSV are deliberately ignored on import.
- The history contains **unflagged partial fills** (e.g. a 0.969-gal top-up) that produce absurd derived MPG (330+). This is expected pending MT-9 (partial-fill flag) — don't "fix" the data.
- `fillups.cost` is nullable (one historical row had a blank cost); new entries require cost > 0. Frontend types cost as `number | null` on reads.
- **The SQLite DB (`data/mileage.db`) is the single source of truth** as of the 2026-07-19 SQL Server backfill (MT-25). New fills are written directly via the app (`POST /api/fillups`). **Do NOT rebuild the DB from the xlsx anymore** — that would drop the 32 backfilled legacy fills and any app-entered rows. Instead, back the DB up: `scripts/export_backup.py` writes a timestamped CSV snapshot to `data/backups/`. `MileageTracker.xlsx` and those CSV snapshots are now *backups/archives*, not inputs.
- `MileageTracker.xlsx` (repo root, capital M) was the seed source before the DB became authoritative: same ledger + deliberate corrections + rows through 2026, plus an unnamed gauge column (H). **Never write to it.** The xlsx adapter (`rows_from_xlsx`) implements a specific policy: ignore formula columns J/K, skip date-only placeholder rows, force `missed_last_fill=1` after a >180-day gap, and reconstruct blank odometers by gallons-weighted interpolation → `mileage_estimated=1`. `scripts/backfill_sqlserver.py` is the one-time legacy-DB merge (needs pyodbc, installed in the backend venv but intentionally not in requirements.txt; see `docs/LEGACY_SQLSERVER.md`).
- `mileage_estimated` rows (and any MPG touching one, exposed as `mpg_estimated`) are badged in the UI (`≈` / `~` prefixes). Estimated-with-flag is the standing policy for missing odometers — Bryan expects more of these in live use. `gauge_notches` is stored raw; its unit calibration is an open question (MT-22).
- Dev database lives at `data/mileage.db` (gitignored). `backend/.env` points `MT_DB_PATH` there.
- Validation lives in two places on purpose: pydantic/router checks server-side (mileage strictly increasing, no future dates, gallons ≤ tank×1.1) and mirrored client-side checks in `QuickLogForm`/`HistoryTable` for instant feedback — change both when changing rules.
- 422 responses come in two shapes: plain-string `detail` (server rules) and pydantic's array (field validation). `api/client.ts` handles both; keep it that way.
- `HistoryTable` delete uses native `window.confirm` — browser-automation tools freeze on it; delete via `DELETE /api/fillups/{id}` when testing.
