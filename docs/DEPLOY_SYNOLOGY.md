# Deploy: Docker on the Synology NAS (build-and-pull CI/CD)

Push-to-deploy for Mileage Tracker. GitHub Actions builds the image and pushes it
to GHCR; **Watchtower** on the DS220+ polls GHCR and auto-updates the container.
Nothing builds on the NAS — it only needs outbound internet to the registry.

Based on the reusable playbook at `flightTracker/docs/ci-cd-docker-nas.md`; this
file is that template with the placeholders filled in for **this** project and the
SQLite-specific bits called out.

## Filled-in values

| Placeholder | Value |
|---|---|
| Owner / repo | `brspencer90` / `mileageTracker` |
| Image | `ghcr.io/brspencer90/mileage-tracker` |
| Build context | repo root (`Dockerfile` at root; needs both `backend/` and `frontend/`) |
| Host:container port | `8088:8000` (change 8088 in `docker-compose.yml` if it clashes) |
| NAS stack dir | `/volume1/docker/mileage-tracker` |
| Runtime secrets | **none today** — SQLite only, no external APIs (add later for MT-14's EIA key) |
| Watchtower poll | 300s |

## The one thing that's different here: SQLite state

The image carries **only code** — the database is **not** baked in. `MT_DB_PATH`
points at `/data/mileage.db`, and `docker-compose.yml` mounts
`{{NAS_STACK_DIR}}/data` → `/data`, so your fill-up history lives on the NAS and
**survives every auto-update**. The container runs as a fixed non-root UID (10001);
the mounted `data/` dir must be writable by it.

**Seed your real data once** (the volume starts empty; a fresh start would give you
an empty DB): copy your local source-of-truth DB up before/after the first `up`:

```bash
# from the dev machine (adjust NAS host)
scp data/mileage.db bryan@<nas>:/volume1/docker/mileage-tracker/data/mileage.db
# then on the NAS, make it owned by the container's UID:
ssh bryan@<nas> 'sudo chown 10001:10001 /volume1/docker/mileage-tracker/data/mileage.db'
```

(Regenerate a CSV backup anytime with `scripts/export_backup.py`; the xlsx and CSVs
stay on disk as backups and are never committed or baked into the image.)

## Files in the repo (already created)

- `Dockerfile` — multi-stage: Node builds the React PWA, then a slim Python image
  runs uvicorn serving the API + built SPA. Non-root UID 10001, `GIT_SHA` build
  stamp, healthcheck hits `/api/health` (which runs `SELECT 1`, so it verifies the DB).
- `.dockerignore` — keeps personal data (`*.xlsx`, `*.csv`, `data/`, `*.db`) and
  secrets out of the image.
- `docker-compose.yml` — the NAS deploy: the app + Watchtower + the `/data` volume.
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

1. `mkdir -p /volume1/docker/mileage-tracker/data`
2. Put `docker-compose.yml` in `/volume1/docker/mileage-tracker/` (or point Container
   Manager at the repo checkout).
3. Seed the DB (see "Seed your real data once" above).
4. Container Manager → **Project → Create** → select the compose file → build/up.
5. Browse `http://<nas>:8088`.

## Verify

```bash
curl -s http://<nas>:8088/api/health     # {"status":"ok","version":"<sha>"}
curl -s http://<nas>:8088/api/version     # {"version":"<sha>"}
# the UI footer shows "ver. <sha7>" — confirm it matches the deployed commit
```

## Day-2

- **Ship an update:** merge to `main` → image builds → Watchtower pulls within 300s.
  Confirm via the version stamp.
- **Force update now:** `sudo docker restart mileage-tracker-watchtower`.
- **Roll back:** pin the last-good tag in `docker-compose.yml`
  (`image: ghcr.io/brspencer90/mileage-tracker:sha-<good>`) and re-up; restore
  `:latest` when fixed.
- **Schema migrations** run automatically at container startup (the FastAPI lifespan
  runs the migration runner against `/data/mileage.db`). They're additive; the volume
  keeps the data across the swap.

## Remote access

Docker changes *how the app is hosted*, not *how you reach it from the pump* — that's
still **Tailscale** (install the Synology package, log in). Browse
`http://<nas-tailnet-name>:8088` from the phone; no ports exposed to the internet.
