@echo off
rem Starts the Mileage Tracker server (API + built frontend) on http://127.0.0.1:8000
rem Run from anywhere, or double-click in Explorer. Ctrl+C (or close window) to stop.
setlocal
cd /d "%~dp0..\backend"

if not exist ".venv\Scripts\uvicorn.exe" (
    echo [error] Backend venv not found at backend\.venv
    echo Create it first from the backend\ folder:
    echo     python -m venv .venv
    echo     .venv\Scripts\pip install -r requirements.txt
    exit /b 1
)

if not exist "..\frontend\dist\index.html" (
    echo [warn] frontend\dist not found - the API will run but the app UI won't be served.
    echo        Build it with:  cd frontend ^&^& npm run build
)

echo Mileage Tracker starting at http://127.0.0.1:8000  (Ctrl+C to stop)
.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000
