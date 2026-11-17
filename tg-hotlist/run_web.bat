@echo off
rem ============================================================
rem  tg-hotlist one-click launcher (Windows)
rem  Double-click this file: starts local server + opens browser.
rem  Close the black window to stop the server.
rem  NOTE: this file is intentionally ASCII-only (cmd.exe cannot
rem  reliably parse UTF-8 Chinese inside a .bat).
rem ============================================================
chcp 65001 >nul
cd /d "%~dp0"
title tg-hotlist local server - close this window to stop

set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

echo.
echo  Starting tg-hotlist local server...
echo  Browser will open automatically in about 3 seconds.
echo.

start "" powershell -NoProfile -Command "Start-Sleep -Seconds 3; Start-Process 'http://127.0.0.1:8765'"

echo  ============================================================
echo   URL: http://127.0.0.1:8765
echo   Close this window to stop the server.
echo   Next time just double-click this file again.
echo  ============================================================
echo.

"%PY%" -X utf8 "%~dp0web_app.py"

echo.
echo  Server stopped.
pause
