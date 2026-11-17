@echo off
rem tg-hotlist side panel - open the web UI as a chromeless Edge window
rem (ASCII-only on purpose: cmd.exe cannot parse UTF-8 Chinese in .bat)
chcp 65001 >nul
cd /d "%~dp0"

set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

rem 1) start backend if not running
powershell -NoProfile -Command "try{(Invoke-WebRequest 'http://127.0.0.1:8765/api/state' -UseBasicParsing -TimeoutSec 2)|Out-Null; exit 0}catch{exit 1}" >nul 2>&1
if errorlevel 1 (
    echo Starting backend...
    start "tg-hotlist backend" /MIN "%PY%" -X utf8 "%~dp0web_app.py"
    timeout /t 5 /nobreak >nul
)

rem 2) find Edge
set "EDGE=C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if not exist "%EDGE%" set "EDGE=C:\Program Files\Microsoft\Edge\Application\msedge.exe"
if not exist "%EDGE%" (
    echo Edge not found. Use run_web.bat instead.
    pause
    exit /b 1
)

rem 3) open as app window (no address bar / tabs)
start "" "%EDGE%" --app=http://127.0.0.1:8765 --window-size=470,980 --user-data-dir="%~dp0.edge-panel" --no-first-run --no-default-browser-check

echo.
echo Panel opened. Use Win+Arrow to snap it next to AyuGram.
echo To pin it on the right, add --window-position=1440,40 above.
