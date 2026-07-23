# Mileage Tracker v2 — Phase 1 (MVP) Implementation Plan

**Status:** Awaiting stakeholder sign-off · **Date:** 2026-07-11 · Companion to [PRODUCT_PLAN.md](PRODUCT_PLAN.md)

**Scope:** MT-1, MT-2, MT-3 (CSV-seed variant), MT-4, MT-6, MT-7, MT-11, plus MT-8 quick-picks (cheap, included) and MT-10 delete/edit-recent (included because the API needs it anyway).

---

## 0. Cross-cutting decisions

| Decision | Choice | Why |
|---|---|---|
| Legacy Streamlit files | Move to `legacy/` (do not delete) | `constants.py` column mapping and `mileage_func.py` semantics are the reference for the later SQL Server migration; delete after MT-3-final. |
| DB access layer | stdlib `sqlite3` (no SQLAlchemy/ORM) | Two tables, one user; an ORM adds a dependency and hides the window-function query we actually need. |
| MPG/MPF storage | **Derived at read time**, never stored | Editing/deleting row N silently corrupts stored MPG of row N+1; deriving via `LAG()` makes edits/deletes/imports always self-consistent. The `missed_last_fill` flag simply nulls the derivation. |
| MPG formula | `mpf / gallons` (current row's gallons — standard full-tank method) | Physically correct: gallons purchased now = fuel burned since last fill. **Note:** the historical CSV divided by the *previous* row's gallons (verified: row 2 MPG 25.32 = 293/11.571, not 293/11.168), so recomputed historical MPG will differ by ~0.5–1.5; this is a correction, not a bug — document it in the importer docstring and expect it in spot-checks. |
| Money | `REAL` dollars, rounded to 2 dp at the API boundary | Cent-integer accounting is overkill for a personal fuel log; matches source data. |
| Schema versioning | `PRAGMA user_version` + numbered SQL files in `backend/app/migrations/`, applied at startup | Zero dependencies; Alembic is heavy for 2 tables. |
| Chart library | **Recharts** | Idiomatic React (declarative, responsive container), SVG renders crisply on mobile; uPlot is lighter but far more effort for two charts. |
| Frontend routing | No router — two views (Log / History) via a bottom tab bar and `useState` | Two views, no deep-link requirement; also removes most SPA-fallback complexity. |
| Frontend data layer | Plain typed `fetch` wrapper, no TanStack Query | ~5 endpoints, one user; caching layers add nothing. |
| CORS | None — Vite dev proxy makes dev same-origin; prod is same-origin by construction | Simplest correct thing; no CORS middleware to misconfigure. |
| PWA offline scope | App-shell precache only; `/api` is network-only; **no offline queue** in Phase 1 | Instant load at the pump is the goal; offline writes are a Phase 2+ feature with real sync complexity. |
| Watchdog | One idempotent `ensure_running.sh` scheduled **at boot AND every 5 min** (health-check → restart) | Single script, single code path; DSM Task Scheduler is the supervisor. A wrapper loop dies with its own process and has no supervisor. |
| Python packaging | `requirements.txt` with pinned versions (plus `requirements-dev.txt`) | The NAS install path is `pip install -r`; no build backend needed. |

---

## 1. Repo layout

```
mileageTracker/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # app factory, router includes, static serving
│   │   ├── config.py            # pydantic-settings
│   │   ├── db.py                # connection helper, pragmas, migration runner
│   │   ├── migrations/
│   │   │   └── 0001_initial.sql
│   │   ├── models.py            # pydantic request/response schemas
│   │   ├── queries.py           # all SQL (incl. the LAG derivation CTE)
│   │   ├── importer.py          # reusable ingestion (see §5)
│   │   └── routers/
│   │       ├── vehicles.py
│   │       ├── fillups.py
│   │       └── stats.py
│   ├── tests/
│   │   ├── conftest.py          # tmp-file SQLite + TestClient fixtures
│   │   ├── fixtures/sample.csv  # committed test fixture (needs .gitignore exception)
│   │   ├── test_importer.py
│   │   ├── test_fillups_api.py
│   │   └── test_stats_api.py
│   ├── requirements.txt         # fastapi, uvicorn[standard], pydantic-settings
│   └── requirements-dev.txt     # pytest, httpx
├── frontend/                    # Vite + React + TypeScript scaffold
│   ├── src/
│   │   ├── api/client.ts        # fetch wrapper + typed endpoint functions
│   │   ├── api/types.ts         # mirrors pydantic response models
│   │   ├── components/
│   │   │   ├── QuickLogForm.tsx
│   │   │   ├── VehiclePicker.tsx
│   │   │   ├── HistoryTable.tsx
│   │   │   ├── MpgChart.tsx
│   │   │   └── CostChart.tsx
│   │   ├── App.tsx              # tab state: "log" | "history"
│   │   └── main.tsx
│   ├── public/                  # PWA icons
│   └── vite.config.ts           # proxy + vite-plugin-pwa
├── scripts/
│   ├── import_csv.py            # CLI: CSV → SQLite via backend/app/importer.py
│   ├── deploy.ps1               # build frontend, scp/rsync to NAS
│   └── nas/
│       ├── ensure_running.sh    # boot + watchdog task
│       ├── rebuild_venv.sh
│       └── snapshot_db.sh       # nightly sqlite .backup for clean Hyper Backup source
├── legacy/                      # moved: app.py, mileage_func.py, constants.py,
│                                #   old requirements.txt, .streamlit/ (empty Dockerfile deleted)
├── docs/
│   ├── PRODUCT_PLAN.md
│   ├── IMPLEMENTATION_PLAN.md
│   └── DEPLOY_SYNOLOGY.md
├── data/                        # gitignored; dev DB lives here
├── mileageTracker.csv           # stays at root (gitignored), seed source
├── CLAUDE.md                    # rewrite in final step
└── .gitignore
```

**.gitignore updates** (append): `data/`, `*.db`, `*.db-wal`, `*.db-shm`, `node_modules/`, `frontend/dist/`, `__pycache__/`, `.pytest_cache/`, `dev-dist/` (vite-plugin-pwa dev artifact), and the exception `!backend/tests/fixtures/*.csv` (root `*.csv` rule would otherwise swallow the test fixture).

---

## 2. SQLite schema (`0001_initial.sql`)

```sql
CREATE TABLE vehicles (
    id            INTEGER PRIMARY KEY,
    name          TEXT NOT NULL UNIQUE,
    make          TEXT,
    model         TEXT,
    year          INTEGER,
    tank_size_gal REAL,                          -- soft cap for gallons validation (legacy hardcoded 13.0)
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE fillups (
    id               INTEGER PRIMARY KEY,
    vehicle_id       INTEGER NOT NULL REFERENCES vehicles(id),
    date             TEXT NOT NULL CHECK (date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    mileage          INTEGER NOT NULL CHECK (mileage > 0),
    gallons          REAL NOT NULL CHECK (gallons > 0),
    cost             REAL NOT NULL CHECK (cost > 0),
    station          TEXT,                        -- nullable: history has blanks
    zip              TEXT CHECK (zip IS NULL OR zip GLOB '[0-9][0-9][0-9][0-9][0-9]'),
    missed_last_fill INTEGER NOT NULL DEFAULT 0 CHECK (missed_last_fill IN (0,1)),
    created_at       TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (vehicle_id, mileage)                  -- also the importer's idempotency key
);

CREATE INDEX idx_fillups_vehicle_date ON fillups (vehicle_id, date);

PRAGMA user_version = 1;
```

- Connection pragmas set in `db.py` on every connection: `PRAGMA foreign_keys=ON; PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;`
- **Migration runner** (in `db.py`, called at FastAPI startup and by the importer CLI): read `PRAGMA user_version`, apply `migrations/000N_*.sql` for `N > version` in order, each inside a transaction, then bump `user_version`. ~25 lines, no library.
- **Derivation query** (lives in `queries.py`, reused by list, single-get, and stats). Ordering axis is `mileage` (the true monotonic axis), not `date`:

```sql
WITH ordered AS (
    SELECT f.*, LAG(mileage) OVER (PARTITION BY vehicle_id ORDER BY mileage) AS prev_mileage
    FROM fillups f
    WHERE vehicle_id = :vehicle_id
)
SELECT *,
    CASE WHEN missed_last_fill = 0 AND prev_mileage IS NOT NULL
         THEN mileage - prev_mileage END                                    AS mpf,
    CASE WHEN missed_last_fill = 0 AND prev_mileage IS NOT NULL
         THEN ROUND((mileage - prev_mileage) / gallons, 2) END              AS mpg
FROM ordered
```

---

## 3. FastAPI backend

### Config (`config.py`, pydantic-settings, reads `.env`)

| Env var | Default | Meaning |
|---|---|---|
| `MT_DB_PATH` | `./data/mileage.db` | SQLite file (parent dir auto-created) |
| `MT_STATIC_DIR` | `../frontend/dist` | Built SPA; if the dir doesn't exist, skip static serving (dev mode) |

Host/port are uvicorn CLI args, not app config.

### Pydantic models (`models.py`)

```python
class VehicleOut:      id, name, make|None, model|None, year|None, tank_size_gal|None
class FillupCreate:    vehicle_id: int; date: date; mileage: int (gt=0)
                       gallons: float (gt=0); cost: float (gt=0)
                       station: str|None; zip: str|None (pattern ^\d{5}$)
                       missed_last_fill: bool = False
class FillupUpdate:    all FillupCreate fields optional (PATCH semantics), minus vehicle_id
class FillupOut:       FillupCreate fields + id, mpf: int|None, mpg: float|None, created_at
class FillupContext:   prev_mileage: int|None; last_station: str|None; last_zip: str|None
                       recent_stations: list[StationPick]   # {station, zip}, 5 most recent distinct
                       tank_size_gal: float|None
class MpgPoint:        date, mileage, mpg|None
class MonthCost:       month: str ("2023-11"), cost: float, gallons: float, fillups: int
```

### Endpoints

| Method/Path | Request | Response | Notes |
|---|---|---|---|
| `GET /api/health` | — | `{"status":"ok"}` | Watchdog target; runs `SELECT 1` against the DB. |
| `GET /api/vehicles` | — | `list[VehicleOut]` | Vehicle creation is out of scope (importer/sqlite3 CLI creates them). |
| `GET /api/fillups?vehicle_id=&limit=50&offset=0` | — | `{items: list[FillupOut], total: int}` | Ordered by mileage DESC. |
| `POST /api/fillups` | `FillupCreate` | `201 FillupOut` (with derived mpf/mpg) | Server validation below. |
| `PATCH /api/fillups/{id}` | `FillupUpdate` | `FillupOut` | For MT-10 typo fixes. |
| `DELETE /api/fillups/{id}` | — | `204` | |
| `GET /api/fillups/context?vehicle_id=` | — | `FillupContext` | Powers MT-7 live MPG preview and MT-8 quick-picks in **one** request at form load; client computes preview MPG as the user types (no per-keystroke round-trips). |
| `GET /api/stats/mpg?vehicle_id=` | — | `list[MpgPoint]` | Derivation CTE, ascending, nulls included (chart gaps at missed fills). |
| `GET /api/stats/cost-by-month?vehicle_id=` | — | `list[MonthCost]` | `GROUP BY strftime('%Y-%m', date)`. |

### Server-side validation (422 with a human message)

- `mileage` strictly `> MAX(mileage)` for that vehicle on POST. On PATCH, `mileage` must stay strictly between the mileage of the neighboring rows (prev < new < next).
- `date` not in the future.
- `gallons <= tank_size_gal * 1.1` if the vehicle has one (soft sanity cap replacing the legacy hardcoded 13.0).
- zip/station: optional; zip pattern enforced by pydantic when present. (Legacy UI required both; history proves they're often absent — server stays permissive, UI nudges.)

### Static serving (`main.py`)

1. Include `/api` routers first.
2. `app.mount("/assets", StaticFiles(directory=dist/"assets"))` for hashed bundles.
3. Explicit routes for `manifest.webmanifest`, `sw.js`, `registerSW.js`, icons (`FileResponse`).
4. Catch-all `GET /{path:path}` → `FileResponse(dist/"index.html")` — SPA fallback that can never shadow `/api` because routes registered earlier win.

Run: `uvicorn app.main:app --host 0.0.0.0 --port 8000` from `backend/`.

---

## 4. Vite React frontend

- Scaffold: `npm create vite@latest frontend -- --template react-ts`.
- **Dev proxy** in `vite.config.ts`: `server.proxy = { "/api": "http://127.0.0.1:8000" }`.
- `api/client.ts`: thin wrapper — `request<T>(method, path, body?)` that throws a typed `ApiError` carrying the server's 422 message; per-endpoint functions.

### Components

- **`App.tsx`** — loads vehicles once; owns `selectedVehicleId` (auto-selects when exactly one) and `activeTab: "log" | "history"`; fixed bottom tab bar (thumb-reachable).
- **`VehiclePicker`** — renders nothing when one vehicle; a `<select>` strip when several.
- **`QuickLogForm`** (the MVP centerpiece) — on mount fetches `/api/fillups/context`. Fields in order: mileage (`inputMode="numeric"`, autofocused), gallons (`inputMode="decimal"`), cost (`inputMode="decimal"`), station + zip pre-filled from last-used with 5 quick-pick chips (MT-8), date defaulted to today (collapsed behind a "change" tap), missed-last-fill checkbox. Live preview line computed client-side from `prev_mileage`: "+293 mi — 25.3 MPG" updates as you type (MT-7). Submit disabled until client-valid; on success show a toast with saved MPG, reset form, refetch context. Server 422 messages render inline.
- **`HistoryTable`** — newest-first; on mobile, stacked cards rather than a wide table; row action menu → edit (small dialog reusing form fields) / delete with confirm (MT-10).
- **`MpgChart`** (Recharts `LineChart`, date x-axis, `connectNulls={false}` so missed-fill gaps show) and **`CostChart`** (Recharts `BarChart`, month x-axis) — both in `ResponsiveContainer`, above the table in the History tab. Consult the `dataviz` skill before writing chart code.

### PWA (`vite-plugin-pwa`)

- `registerType: "autoUpdate"`, manifest: name "Mileage Tracker", `display: "standalone"`, theme color, 192/512 + maskable icons.
- Workbox: precache the built shell; `navigateFallback: "index.html"` with `navigateFallbackDenylist: [/^\/api\//]`; **no runtime caching for `/api`** (network-only — stale fill-up data is worse than a spinner).
- Result: instant shell load from cache at the pump; API calls still require the tailnet — accepted MVP behavior.

---

## 5. CSV seed importer (MT-3, reusable for the SQL Server migration)

**Architecture:** `backend/app/importer.py` owns the *sink*; source adapters produce normalized dicts. The later SQL Server migration is just a second adapter feeding the same `import_fillups()`.

```python
NormalizedRow = TypedDict("NormalizedRow", {
    "vehicle_name": str, "date": str,        # ISO YYYY-MM-DD
    "mileage": int, "gallons": float, "cost": float,
    "station": str | None, "zip": str | None, "missed_last_fill": bool,
})
def import_fillups(conn, rows: Iterable[NormalizedRow]) -> ImportReport: ...
    # get-or-create vehicles by name; INSERT OR IGNORE keyed on UNIQUE(vehicle_id, mileage)
    # → naturally idempotent; single transaction
    # ImportReport = {inserted, skipped_existing, vehicles_created, warnings}
def rows_from_legacy_csv(path) -> Iterator[NormalizedRow]: ...
```

`rows_from_legacy_csv` handling (all verified against the real file):

- Open with `encoding="utf-8-sig"` — the file has a UTF-8 BOM.
- **Header normalization is case-insensitive**: the actual header is `Zip code`, not `Zip Code` as `legacy/constants.py` claims. Map by `header.strip().lower()`.
- `#N/A` and empty strings → `None` (use `csv` module, not pandas — no NA-coercion surprises, no numpy dependency).
- Zip: strip a trailing `.0` (float-parsed zips), left-pad to 5 with zeros, else `None` if it doesn't match `\d{5}`.
- Date `MM/DD/YYYY` → ISO.
- **Ignore the stored `MPF`/`MPG` columns** (derived in v2). Optionally cross-check and append a warning when `|stored − recomputed_with_prev_gallons| > 0.05` — catches parse errors without failing on the known formula difference.
- First-ever row has `missed_last_fill=1` in the data; import as-is (derivation nulls its MPG anyway).

**CLI** `scripts/import_csv.py`: `python scripts/import_csv.py mileageTracker.csv --db data/mileage.db [--dry-run]` — runs migrations first, prints the `ImportReport`, exits nonzero if `inserted == 0 and skipped == 0`.

---

## 6. Testing

- **pytest only, backend only** (MVP). `conftest.py`: fixture creating a migrated tmp-file SQLite + `TestClient` with `MT_DB_PATH` overridden.
- `test_importer.py`: fixture CSV containing BOM, `#N/A`, blank station, float zip, missed-fill row → assert normalization, derived MPG correctness, and idempotency (run twice, `skipped_existing == n`).
- `test_fillups_api.py`: create happy path returns derived mpf/mpg; mileage ≤ max rejected 422; future date rejected; PATCH neighbor-bounds; DELETE; context endpoint shape/quick-picks.
- `test_stats_api.py`: month grouping and null-MPG gap at a missed fill.
- **Frontend: no unit tests in Phase 1.** TypeScript + end-to-end verification is the right cost/benefit for a single-user MVP.

---

## 7. `docs/DEPLOY_SYNOLOGY.md` runbook (write with these sections and exact scripts)

1. **Prereqs:** DSM 7.x on DS220+ (Gemini Lake x86_64), SSH enabled, admin user.
2. **Python:** Package Center → Settings → Package Sources → add SynoCommunity (`https://packages.synocommunity.com`) → install **Python 3.12** (geminilake build; verify path via `ls /usr/local/bin/python3*`).
3. **Folder layout:** shared folder `apps` → `/volume1/apps/mileage-tracker/{backend, frontend/dist, data, data/backups, logs, scripts}`. Run everything as user `bryan`; `chown -R bryan` the tree (boot task must run as this user — known DSM gotcha).
4. **Deploy from dev machine** (`scripts/deploy.ps1`): `npm run build` in `frontend/`, then `scp -r` `backend/app`, `backend/requirements.txt`, `frontend/dist`, `scripts/nas/*` to the NAS. **Never touches `data/`.**
5. **venv (over SSH):** run `scripts/nas/rebuild_venv.sh` (idempotent — also the MT-5 upgrade fix):
   ```sh
   #!/bin/sh
   APP=/volume1/apps/mileage-tracker
   PY=$(command -v python3.12 || command -v python3.13)
   rm -rf "$APP/venv"
   "$PY" -m venv "$APP/venv"
   "$APP/venv/bin/pip" install --upgrade pip
   "$APP/venv/bin/pip" install -r "$APP/backend/requirements.txt"
   ```
6. **.env** at `/volume1/apps/mileage-tracker/backend/.env`: `MT_DB_PATH=/volume1/apps/mileage-tracker/data/mileage.db`, `MT_STATIC_DIR=/volume1/apps/mileage-tracker/frontend/dist`.
7. **Seed:** `venv/bin/python scripts/import_csv.py mileageTracker.csv --db .../data/mileage.db` (copy the CSV up once).
8. **Start + watchdog — one script**, `scripts/nas/ensure_running.sh`:
   ```sh
   #!/bin/sh
   APP=/volume1/apps/mileage-tracker
   if curl -sf -m 5 http://127.0.0.1:8000/api/health >/dev/null; then exit 0; fi
   pkill -f "uvicorn app.main:app" 2>/dev/null; sleep 2
   cd "$APP/backend"
   nohup "$APP/venv/bin/uvicorn" app.main:app --host 0.0.0.0 --port 8000 \
       >> "$APP/logs/app.log" 2>&1 &
   ```
   Two DSM Task Scheduler entries, both **user = bryan**, both running this script: (a) Triggered task, event = Boot-up; (b) Scheduled task, every 5 minutes. Idempotence means the boot task and watchdog can never fight; MT-1's 5-minute recovery AC falls out for free.
9. **Nightly DB snapshot** (`scripts/nas/snapshot_db.sh`, scheduled 03:00): uses the venv python's `sqlite3 Connection.backup()` to write `data/backups/mileage-YYYYMMDD.db`, keep last 14 — gives Hyper Backup a consistent non-WAL file.
10. **Hyper Backup:** include `/volume1/apps/mileage-tracker/data` in the existing backup task. **Restore procedure** (write down, test once per MT-4): disable both tasks → copy snapshot over `data/mileage.db` (remove `-wal`/`-shm`) → run ensure_running.sh → verify `/api/health` and row count.
11. **Tailscale:** install official package from Package Center, log in, note the NAS tailnet name/IP; enable "run at boot". No firewall/port-forward changes.
12. **Phone:** install Tailscale app, log in, enable always-on/on-demand; open `http://<nas-tailnet-name>:8000`, verify, then Add to Home Screen (PWA manifest installs standalone).

---

## 8. Verification plan

**Dev machine (Windows), before any NAS work:**
1. `pytest` green in `backend/`.
2. `python scripts/import_csv.py mileageTracker.csv` → report matches CSV row count (minus header); run again → all `skipped_existing`.
3. Terminal A: `uvicorn app.main:app --reload`; Terminal B: `npm run dev`. Open `http://localhost:5173` in Chrome DevTools mobile emulation: log a fill-up typing only mileage/gallons/cost — verify live MPG preview, numeric keyboards (`inputMode` in DOM), success toast; verify History tab + both charts per-vehicle; edit then delete the test row.
4. **Production-mode rehearsal:** `npm run build`, stop Vite, hit `http://localhost:8000` directly — SPA loads from FastAPI; run Lighthouse PWA check (installable, manifest, SW registered).
5. Spot-check 3 recomputed MPG values against the CSV, expecting the documented prev-vs-current-gallons delta.

**NAS smoke test (after runbook §1–12):**
1. `curl http://<nas-lan-ip>:8000/api/health` → ok; open UI, confirm seeded history/charts.
2. Kill uvicorn over SSH → confirm the 5-min task revives it (MT-1 crash AC).
3. Reboot the NAS → app reachable within ~2 min (MT-1 boot AC).
4. Phone on LTE (Wi-Fi off) + Tailscale on → load home-screen icon, log a real test fill-up (MT-2 + definition-of-done rehearsal), then delete it.
5. Confirm the next Hyper Backup run includes `data/`; perform the documented restore once (MT-4).

---

## 9. Ordered implementation steps

| # | Step | Runnable state after | Size |
|---|---|---|---|
| 1 | Repo restructure: move Streamlit files + `.streamlit/` + old `requirements.txt` to `legacy/`, delete empty `Dockerfile`, update `.gitignore`, create dir skeleton | Clean tree, nothing broken | S (~30 min) |
| 2 | Backend skeleton: `config.py`, `db.py` (pragmas + migration runner), `0001_initial.sql`, `main.py` with `/api/health`; pytest scaffold | `uvicorn` serves `/api/health`; migration applies | S (~1–2 h) |
| 3 | Importer: `importer.py` + `scripts/import_csv.py` + fixture CSV + tests | Real CSV seeds a dev DB, idempotent | M (~2–3 h) |
| 4 | Core API: models, `queries.py` derivation CTE, vehicles/fillups routers (CRUD + context), validation, tests | Full API usable via `/docs` | M (~3–4 h) |
| 5 | Stats endpoints + tests | `/api/stats/*` chart-ready | S (~1 h) |
| 6 | Frontend scaffold: Vite+TS, proxy, `client.ts`/`types.ts`, `App.tsx` tabs, `VehiclePicker`, **`QuickLogForm`** with live preview + quick-picks | Log a fill-up end-to-end in dev | L (~4–6 h) |
| 7 | History tab: `HistoryTable` (cards on mobile, edit/delete) + Recharts charts | MT-10, MT-11 done in dev | M (~3–4 h) |
| 8 | PWA + prod serving: vite-plugin-pwa, icons, FastAPI static mount + SPA fallback; production-mode rehearsal | Installable app served by uvicorn alone | S–M (~2 h) |
| 9 | Write `docs/DEPLOY_SYNOLOGY.md` + `scripts/nas/*` + `deploy.ps1` | Runbook ready | M (~2 h) |
| 10 | NAS deployment following the runbook + smoke test §8 | MT-1/2/3/4 verified live | M (half day incl. Tailscale/phone) |
| 11 | Rewrite `CLAUDE.md` for the new stack; note `legacy/` retirement condition | Docs current | S (~30 min) |

Something is runnable after every step; steps 3–5 and 6–7 can interleave, but 4 must precede 6.
