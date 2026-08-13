# Deploy: Docker on the Synology NAS (build-and-pull CI/CD)

Push-to-deploy for Mileage Tracker. GitHub Actions builds the image and pushes it
to GHCR; **Watchtower** on the DS220+ polls GHCR and auto-updates the container.
Nothing builds on the NAS — it only needs outbound internet to the registry.

Based on the reusable playbook at `flightTracker/docs/ci-cd-docker-nas.md`; this
file is that template with the placeholders filled in for **this** project.

## Filled-in values

| Placeholder | Value |
|---|---|
| Owner / repo | `brspencer90` / `mileageTracker` |
| Image | `ghcr.io/brspencer90/mileage-tracker` |
| Build context | repo root (`Dockerfile` at root; needs both `backend/` and `frontend/`) |
| Host:container port | `8124:8000` (change 8124 in `docker-compose.yml` if it clashes) |
| NAS stack dir | `/volume1/docker/mileage-tracker` |
| Runtime secret | `sqlss_conn_str` — the SQL Server connection string (in a git-ignored `mileage-tracker.env` on the NAS) |
| Watchtower poll | 300s |

## Database: SQL Server (stateless container)

The app's data lives in **Microsoft SQL Server at `192.168.0.20`** — the v2
`vehicles`/`fillups` tables in the `mileageTracker` DB (the legacy `mileage` table
is left alone). The **container is stateless**: no volume, no local DB. It reads
the connection string from `sqlss_conn_str` at runtime, and `run_schema` creates
the tables on first connect if they don't exist.

**Your 205 fills are already migrated into SQL Server** (via
`scripts/migrate_sqlite_to_sqlserver.py`, run once from the dev machine) — so there
is **no seed step on the NAS**. The container just needs the connection string.
(The pre-migration SQLite snapshots remain in `data/backups/` as a safety net.)

The one config file you create on the NAS is `mileage-tracker.env`:
```
sqlss_conn_str = 'SERVER={192.168.0.20,1433};DATABASE={mileageTracker};UID={SA};PWD=...'
```
(Same value as your dev-machine `.env`. Note the brace-quoted `SERVER={host,port}` —
that's the ODBC form the app expects.)

## Files in the repo (already created)

- `Dockerfile` — multi-stage: Node builds the React PWA, then a slim Python image
  (with the **Microsoft ODBC Driver 18** baked in) runs uvicorn serving the API +
  built SPA. Non-root UID 10001, `GIT_SHA` build stamp, healthcheck hits
  `/api/health` (which runs `SELECT 1` against SQL Server, so it verifies the DB).
- `.dockerignore` — keeps personal data (`*.xlsx`, `*.csv`, `*.db`) and secrets out of the image.
- `docker-compose.yml` — the NAS deploy: the app + Watchtower, connection string via `env_file`.
- `.github/workflows/ci.yml` — PR check `validate`: backend pytest, frontend
  typecheck/lint/build, and an image build (no push). Required for merge.
- `.github/workflows/deploy.yml` — on push to `main`: build + push `:latest` and
  `:sha-xxxxxxx` to GHCR with `GIT_SHA`.
- `.github/CODEOWNERS`, `scripts/setup-branch-protection.sh`.

## One-time setup

### 1. GitHub (bootstrap order matters)

1. Push these files **straight to `main`** first (the `validate` check must exist
   before the branch can require it).
2. Let `deploy.yml` run once → it creates the private package
   `ghcr.io/brspencer90/mileage-tracker`.
3. **Package visibility:** default is **private** (recommended — it bundles your app
   code). Then the NAS needs a read token (step 2.1). The image holds no personal
   data, so you *may* set it public to skip registry auth entirely
   (GitHub → Packages → the package → Package settings → visibility).
4. **Protect `main`:** `gh auth login && bash scripts/setup-branch-protection.sh`.
   (Requires the `gh` CLI, which isn't on this dev box — install it or run from one
   that has it.) From here, changes flow through PRs gated by `validate`, self-merge allowed.

### 2. NAS (Synology Container Manager)

**2.1 Registry auth — only if the package is private.** A classic PAT with **only**
`read:packages`. Log the Docker daemon in over SSH (Watchtower reuses the same file):

```bash
printf '%s' 'ghp_YOURTOKEN' | sudo docker login ghcr.io -u brspencer90 --password-stdin
# expect: Login Succeeded  -> credential saved to /root/.docker/config.json
```

**2.2 Deploy.**

1. `mkdir -p /volume1/docker/mileage-tracker`
2. Put `docker-compose.yml` in `/volume1/docker/mileage-tracker/` (or point Container
   Manager at the repo checkout).
3. Create `mileage-tracker.env` next to it with the connection string (see the DB
   section above). No data seeding — your 205 fills are already in SQL Server.
4. Container Manager → **Project → Create** → select the compose file → build/up.
5. Browse `http://<nas>:8124`.

*(If the SQL Server itself runs on this same NAS, the container reaches it over the
LAN IP `192.168.0.20` from the default bridge network — no special networking needed.)*

## Verify

```bash
curl -s http://<nas>:8124/api/health     # {"status":"ok","version":"<sha>"}
curl -s http://<nas>:8124/api/version     # {"version":"<sha>"}
# the UI footer shows "ver. <sha7>" — confirm it matches the deployed commit
```

## Day-2

- **Ship an update:** merge to `main` → image builds → Watchtower pulls within 300s.
  Confirm via the version stamp.
- **Force update now:** `sudo docker restart mileage-tracker-watchtower`.
- **Roll back:** pin the last-good tag in `docker-compose.yml`
  (`image: ghcr.io/brspencer90/mileage-tracker:sha-<good>`) and re-up; restore
  `:latest` when fixed.
- **Schema** is applied automatically at container startup (`run_schema` runs the
  idempotent `app/schema.sql` against SQL Server). Since old and new containers briefly
  share the one SQL Server during a Watchtower swap, keep schema changes additive.

## Remote access

Docker changes *how the app is hosted*, not *how you reach it from the pump* — that's
still **Tailscale** (install the Synology package, log in). Browse
`http://<nas-tailnet-name>:8124` from the phone; no ports exposed to the internet.
