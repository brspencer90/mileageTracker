# Mileage Tracker — one image: FastAPI + SQLite serving the built React PWA.
# Build context is the REPO ROOT (it needs both frontend/ and backend/):
#   docker build -t mileage-tracker .
#
# The SQLite DB is NOT baked in — it lives on a mounted volume at /data
# (MT_DB_PATH), so your fill-up history survives image updates. See
# docs/DEPLOY_SYNOLOGY.md for the one-time data seed.

# ---- stage 1: build the frontend (Vite/React -> dist) ----
FROM node:22-alpine AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build            # emits /fe/dist (SPA + PWA artifacts)

# ---- stage 2: python runtime ----
FROM python:3.12-slim
# Non-root fixed UID so the mounted /data volume has predictable ownership on the NAS.
RUN groupadd -g 10001 app && useradd -u 10001 -g app -M -s /usr/sbin/nologin app
WORKDIR /srv

# Backend deps first for layer caching (requirements.txt deliberately has no
# pyodbc — the v2 app uses SQLite only; pyodbc lives with the legacy tooling).
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# App code (tracked source only) + the built SPA from stage 1.
COPY backend/app ./app
COPY --from=frontend /fe/dist ./frontend/dist

ARG GIT_SHA=dev
ENV GIT_SHA=$GIT_SHA \
    MT_DB_PATH=/data/mileage.db \
    MT_STATIC_DIR=/srv/frontend/dist \
    PORT=8000 \
    PYTHONUNBUFFERED=1

# /data is the volume mount point for the SQLite DB; make it writable by the app user.
RUN mkdir -p /data && chown -R app:app /data /srv
USER 10001
EXPOSE 8000

# Healthcheck hits /api/health, which runs SELECT 1 — so it verifies the DB, not
# just that the process is alive. Uses stdlib urllib (no curl dependency).
HEALTHCHECK --interval=30s --timeout=5s --start-period=12s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=4).status==200 else 1)"

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
