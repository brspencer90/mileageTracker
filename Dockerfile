# Mileage Tracker — one image: FastAPI serving the built React PWA, backed by
# the SQL Server at 192.168.0.20 (via pyodbc + ODBC Driver 18).
# Build context is the REPO ROOT (it needs both frontend/ and backend/):
#   docker build -t mileage-tracker .
#
# No database is baked in or mounted: the connection string (sqlss_conn_str) is
# injected at runtime from a git-ignored env file on the NAS. See
# docs/DEPLOY_SYNOLOGY.md.

# ---- stage 1: build the frontend (Vite/React -> dist) ----
FROM node:22-alpine AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build            # emits /fe/dist (SPA + PWA artifacts)

# ---- stage 2: python runtime ----
FROM python:3.12-slim
RUN groupadd -g 10001 app && useradd -u 10001 -g app -M -s /usr/sbin/nologin app

# Microsoft ODBC Driver 18 + unixODBC — pyodbc needs these at runtime to reach
# the SQL Server (192.168.0.20). python:3.12-slim is Debian 12 (bookworm).
RUN apt-get update && apt-get install -y --no-install-recommends curl gnupg ca-certificates \
 && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
 && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/mssql-release.list \
 && apt-get update && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 unixodbc \
 && apt-get purge -y --auto-remove curl gnupg && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

# Backend deps first for layer caching.
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# App code (tracked source only) + the built SPA from stage 1.
COPY backend/app ./app
COPY --from=frontend /fe/dist ./frontend/dist

ARG GIT_SHA=dev
ENV GIT_SHA=$GIT_SHA \
    MT_STATIC_DIR=/srv/frontend/dist \
    PORT=8000 \
    PYTHONUNBUFFERED=1
# The SQL Server connection string (sqlss_conn_str) is injected at RUNTIME from
# the NAS env file — never baked in. No local DB / volume anymore.

RUN chown -R app:app /srv
USER 10001
EXPOSE 8000

# Healthcheck hits /api/health, which runs SELECT 1 — so it verifies the DB, not
# just that the process is alive. Uses stdlib urllib (no curl dependency).
HEALTHCHECK --interval=30s --timeout=5s --start-period=12s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=4).status==200 else 1)"

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
