# Mileage Tracker v2 — Product Plan

**Product owner:** Claude (PO/PM) · **End user / stakeholder:** Bryan · **Date:** 2026-07-10 · **Status:** Decisions ratified by stakeholder 2026-07-10; Smartcar/EIA/DS220+ facts verified same day

## 1. Vision

A self-hosted fuel and vehicle-cost tracker that lives on Bryan's Synology NAS, is reachable securely from his phone anywhere, and makes logging a fill-up at the pump take under 30 seconds. Over time it grows from a log into an insight engine: fuel-economy trends as an early-warning signal for vehicle health, and context on whether each fill-up was a good deal.

## 2. Users & scope

- **Primary (only) user:** Bryan. No multi-user auth inside the app; access control is handled at the network layer (VPN).
- **Vehicles:** 1 today, but the data model and UI must support multiple vehicles from day one (vehicle entity + picker) so adding a car later is a data change, not a code change.
- **History:** all existing records migrate from SQL Server into the new database; SQL Server is then retired.

## 3. Key decisions (research-backed)

| Decision | Choice | Rationale | Runner-up |
|---|---|---|---|
| Hosting (no Docker) | SynoCommunity Python 3.12/3.13 + venv on `/volume1` + Task Scheduler boot task running uvicorn | Only non-Docker path for a long-running Python server; well documented; survives DSM updates if kept out of system paths. NAS is a DS220+ (Intel Gemini Lake x86_64) — SynoCommunity python312 (3.12.13) and python313 both verified available for the geminilake arch on DSM 7.1+ | Virtual Machine Manager (bulletproof but needs Btrfs + ~2 GB RAM — overkill) |
| Remote access | **Tailscale** (official Synology package) — **ratified** | Zero exposed ports, install-and-login setup, phone app can stay always-on; matches Bryan's VPN preference and won the research comparison | Cloudflare Tunnel via SynoCommunity `cloudflared` + Cloudflare Access (always-on public URL, but needs a domain and exposes the app behind CF auth) |
| Database | **SQLite** on `/volume1` — **ratified** | Stdlib, zero services to babysit, backed up with normal NAS backups; right-sized for single user. Synology's MariaDB package is EOL (10.3.37, unpatched since 2023) — avoided | MariaDB package (only if a real DB server is ever needed) |
| App framework | **Vite + React PWA front end, FastAPI back end** — stakeholder opted off Streamlit | Instant-loading, installable-to-home-screen mobile UX (the 30-second pump goal); FastAPI serves both the JSON API and the built static files from one uvicorn process. Front end is built on the dev machine — only the `dist/` output deploys to the NAS, so no Node.js needed on the DS220+ | Streamlit (known stack, but heavier/slower on mobile and hard to make PWA-installable) |
| Web Station / QuickConnect | **Ruled out** | Web Station is WSGI-only (can't run Streamlit); QuickConnect only relays Synology's own services | — |

Known operational gotchas to design around: no crash-restart supervision from Task Scheduler (add a watchdog/restart task); venv may need recreating after a SynoCommunity Python package upgrade (document a rebuild script); run the boot task as a user with permissions on the project folder.

## 4. Epics & user stories

Priorities: **M** = Must (MVP), **S** = Should, **C** = Could, **W** = Won't (this phase).

### Epic 1 — Platform: NAS hosting, remote access, data migration

- **MT-1 (M)** As Bryan, I want the app running on my NAS and starting automatically on boot, so it's always available without my PC. *AC: NAS reboots → app reachable within 2 min with no manual action; app crash is auto-recovered by a watchdog within 5 min.*
- **MT-2 (M)** As Bryan, I want to open the dashboard from my phone anywhere via Tailscale, so I can log at the pump. *AC: with Tailscale on, the bookmarked/home-screen URL loads over LTE away from home; NAS has no ports forwarded to the internet.*
- **MT-3 (M, adjusted)** As Bryan, I want the new database seeded from `mileageTracker.csv` now for testing, with a reusable import path so the full SQL Server history (server currently powered off) can be migrated later before cutover. *AC: idempotent CSV import script; row counts and MPG spot-checks match the CSV; the same ingestion path can accept the SQL Server export later.*
- **MT-4 (M)** As Bryan, I want the database included in my NAS backup routine, so a disk failure doesn't lose my history. *AC: SQLite file lives in a backed-up shared folder; restore procedure written down and tested once.*
- **MT-5 (S)** As Bryan, I want a documented rebuild script (venv + dependencies), so a DSM/Python package upgrade is a 5-minute fix, not an archaeology dig.

### Epic 2 — Quick logging at the pump (mobile-first)

- **MT-6 (M)** As Bryan at the pump, I want a phone-friendly entry form where I only type mileage, gallons, and cost, so logging takes under 30 seconds. *AC: vehicle defaults to my (only) car; date defaults to today; form is thumb-usable on a phone without horizontal scrolling; numeric keyboards for numeric fields.*
- **MT-7 (M)** As Bryan, I want the same validation as today (mileage > previous max, 5-digit zip, cost/gallons > 0) plus a confirmation of the computed MPG before saving, so bad entries don't pollute trends. *AC: save disabled until valid; MPG/miles-since-last-fill shown pre-save; success feedback after save.*
- **MT-8 (S)** As Bryan, I want the gas station and zip to pre-fill from my most frequent/last-used values, so repeat stations are one tap. *AC: last 5 stations offered as quick picks.*
- **MT-9 (S)** As Bryan, I want to flag partial fills and missed fills, so MPG math stays honest (partial fills roll into the next full fill's MPG). *AC: MPG not computed across partial/missed boundaries; flagged rows visibly marked.*
- **MT-10 (S)** As Bryan, I want to edit or delete a recent entry, so a typo at the pump isn't permanent.

### Epic 3 — Dashboard & insights

- **MT-11 (M)** As Bryan, I want the fill-up history table (as today) plus MPG-over-time and cost-per-month charts, so I can see trends at a glance. *AC: charts render on phone and desktop; per-vehicle when multiple exist.*
- **MT-12 (S)** As Bryan, I want headline stats — lifetime cost, cost/mile, average MPG, best/worst tank, average days between fills — so the data tells me something without digging.
- **MT-13 (C)** As Bryan, I want a seasonal overlay on the MPG chart (winter vs summer blend), so I don't mistake seasonal dips for problems.

### Epic 4 — Data enrichment (the "what else can we do" ideas, feasibility-checked)

- **MT-14 (S)** **Price benchmark:** As Bryan, I want each fill-up compared to the EIA weekly regional average, so I know if I got a good deal. *AC: free EIA API key; weekly cached fetch; each entry shows ± vs region. Bryan is in Houston, TX (77007) — Houston is one of the ~10 metros EIA publishes weekly, so we get metro-level granularity (verified series IDs: Houston `EMM_EPMR_PTE_Y44HO_DPG`, Texas fallback `EMM_EPMR_PTE_STX_DPG`, via API v2 route `petroleum/pri/gnd/data/`). (Station-level "neighbors" comparison is not feasible without paid scraper APIs — GasBuddy has no public API; parked as W.)*
- **MT-15 (S)** **Health monitor:** As Bryan, I want an alert when my rolling MPG drops sustainedly below trend, so I catch problems (tire pressure, O2 sensor) early. *AC: rolling average with threshold; visible banner on dashboard when triggered; seasonally aware once MT-13 exists.*
- **MT-16 (W)** **Smartcar integration:** ruled out after verification. Smartcar's US Volkswagen support only covers ~MY2020+ (the myVW / Car-Net 2.0 generation); Bryan's 2019 GTI is the older Car-Net generation whose 3G connectivity was sunset in Feb 2022 and never appears in Smartcar's compatibility matrix. Automatic odometer reads are off the table — the OBD-II path (MT-17) is the realistic vehicle-data source and inherits this story's priority (C).
- **MT-17 (C)** **OBD-II import:** As Bryan, I want to import Car Scanner/Torque CSV exports (from a ~$15 ELM327 dongle), so I get real trip speed/engine data. *(This replaces both the Google Maps idea — Google Timeline is on-device-only in 2026, no Takeout, no API — and the Smartcar idea (MT-16); both parked as W.)*
- **MT-18 (C)** **Maintenance log:** As Bryan, I want to record maintenance events (oil change, tires) with time/mileage reminders, so the app tracks total cost of ownership, not just fuel.

### Epic 4b — New source file & data reconstruction (added 2026-07-12; MT-20/21 shipped 2026-07-18)

- **MT-20 (M)** **xlsx import adapter:** As Bryan, I want `MileageTracker.xlsx` to replace the CSV as the import source, so my 74 newer fill-ups (through Jul 2026) and my manual corrections come in. *Adapter policy (validated by investigation): openpyxl `data_only=True`; ignore formula columns J/K; default Car to Tiger; blank Missed flag → 0; skip empty placeholder rows 102/129 (logged); force `missed_last_fill=1` on row 101 (first fill after the unrecorded Nov 2023–Sep 2024 gap); import unnamed column H raw as nullable `gauge_notches`.*
- **MT-21 (M)** **Estimated-mileage support:** As Bryan, I want the two real fills missing odometer readings (May 19/23, 2026) imported with reconstructed mileage instead of dropped, so no interval silently spans multiple tanks. *Method: gallons-weighted interpolation, holdout-validated (median error ~8–10 mi, p95 ~±32, worst ~75 over 183 reconstructions). Estimates: 68,479 and 68,730 mi. Schema: `mileage_estimated` flag; UI badges estimated rows and their derived MPG.*
- **MT-22 (C)** **Gauge-based partial-fill detector:** the H column tracks pre-fill fuel remaining well (gallons ≈ 11.81 − 1.12·H, R² 0.94) but adds no mileage-estimation value beyond recorded gallons. Keep it for flagging probable partial fills (actual gallons ≥ ~0.75 below the H-predicted amount) — feeds MT-9. *Answered 2026-07-19: the gauge has **8 major divisions** (not 5), each split into quarters — brim-full reads 8.0. The low-range linear fit (gallons ≈ 11.81 − 1.12·H) extrapolates to ~2.9 gal still needed at H=8, so the gauge is nonlinear near Full; calibration should be piecewise/empirical and will improve as high-H readings accumulate. Bryan also endorsed auto-SUGGESTING missed/partial flags from data rather than silently setting them (applies to MT-9's UX).*

### Epic 2b — Next stage (recorded 2026-07-19 from stakeholder feedback)

- **MT-23 (M, bug)** **History edit loses place + silent consequences:** As Bryan, when I've paged down with "Load more" and edit a row, I want to stay where I was (no jump to top / full reload), see confirmation of what changed, and see what my edit affects afterward (derived MPG of this row and the next shift when mileage/gallons change). *AC: after saving an edit, the list keeps loaded pages and scroll position, updates the edited card in place (plus the following card's derived values), and shows a confirmation naming the changed fields and any knock-on MPG changes.*
- **MT-24 (S)** **In-app mileage backfill:** As Bryan, when I logged a fill without an odometer reading (it happens at the pump), I want the app to offer to reconstruct it later — same gallons-weighted interpolation as import, triggered once bracketing fills exist, stored with the `mileage_estimated` badge. *Depends on allowing fill creation without mileage; suggestion UX per the MT-9 principle: suggest, never silently set.*
- **MT-25 (M — was C; reconciliation run 2026-07-19)** **SQL Server backfill:** the read-only reconciliation (see `docs/LEGACY_SQLSERVER.md`) found **~32 real fills in the old DB that the xlsx is missing** — the Nov 2023–Sep 2024 "gap" was a copy failure, not a recording gap. Also confirmed the 2023-10-05 estimate (37,399) vs the DB's real 37,400 (estimator off by 1 mi), and that the two corrected 2022 rows are *right* in the xlsx and *wrong* in the DB. **DONE 2026-07-19:** 32 gap fills merged into SQLite via `scripts/backfill_sqlserver.py` (204 rows total, monotonic, gap-boundary 57-MPG spike resolved). Two corrections applied (2023-10-05 real 37,400; obsolete gap flag cleared). Per Bryan's direction, **the SQLite DB is now the single source of truth**; xlsx + `scripts/export_backup.py` CSV snapshots are backups. See `docs/LEGACY_SQLSERVER.md`.

### Epic 5 — Stretch: faster-than-typing capture

- **MT-19 (W→C later)** Receipt-photo capture: snap the pump receipt, OCR extracts gallons/cost/station. Revisit after MVP proves out; meaningful build effort.

## 5. Roadmap

- **Phase 1 — MVP (Epics 1–2 + MT-11):** platform live on NAS, Tailscale access, history migrated, mobile quick-log, basic charts. *Definition of done: Bryan logs a real fill-up at a real gas station from his phone.*
  - *Status 2026-07-11:* local build complete and verified end-to-end (MT-3 CSV seed, MT-6/7/8/10/11 working in browser; 27 backend tests green). NAS deployment (MT-1/2/4) deferred at stakeholder request. **PO recommendation:** pull MT-9 (partial-fill flag) into the next iteration — verification exposed 2 unflagged partial fills in the history producing absurd derived MPG (330/105), which the old spreadsheet formula had masked.
- **Phase 2 — Insights (rest of Epic 3 + MT-14, MT-15):** stats, price benchmark, health monitor.
- **Phase 3 — Enrichment (MT-17, MT-18, MT-19):** OBD-II import, maintenance log, receipt OCR — reprioritize based on Phase 2 usage. (Smartcar MT-16 dropped: incompatible with the 2019 GTI.)

## 6. Stakeholder answers (2026-07-10)

1. **NAS:** Synology DS220+ — Intel Celeron J4025 (Gemini Lake, x86_64), 2 GB RAM stock (expandable to 6 GB; not needed for this app). Verified: SynoCommunity python312/python313 available for geminilake on DSM 7.1+.
2. **Vehicle:** 2019 VW GTI (MK7.5). Verified NOT Smartcar-compatible (US VW support starts ~MY2020; pre-2020 Car-Net was 3G-sunset in 2022) — MT-16 moved to Won't.
3. **Location:** Houston, TX 77007 — covered by EIA's Houston metro weekly series (see MT-14).
4. **Migration:** old SQL Server exists but is powered off. Phase 1 seeds from `mileageTracker.csv` for testing; full history migration happens later via the same import path (MT-3 adjusted).
5. **Front end:** stakeholder is happy to move off Streamlit — ratified Vite + React PWA + FastAPI (section 3).
