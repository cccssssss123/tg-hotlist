@echo off
rem ============================================================
rem  Start tg-hotlist backend + exDesktop together
rem  (ASCII-only on purpose: cmd.exe cannot parse UTF-8 Chinese)
rem ============================================================
chcp 65001 >nul
cd /d "%~dp0"

set "BACKEND_DIR=%~dp0..\tg-hotlist"
set "PY=%BACKEND_DIR%\.venv\Scripts\python.exe"
set "EXD=%~dp0app\Telegram.exe"

echo.
echo  ============================================================
echo   tg-hotlist + exDesktop launcher
echo  ============================================================
echo.

if not exist "%EXD%" goto no_exd
if not exist "%PY%" goto no_py

powershell -NoProfile -Command "try{(Invoke-WebRequest 'http://127.0.0.1:8765/api/state' -UseBasicParsing -TimeoutSec 2)|Out-Null; exit 0}catch{exit 1}" >nul 2>&1
if errorlevel 1 goto start_backend

echo  Backend already running.
goto start_exd

:start_backend
echo  Starting tg-hotlist backend...
start "tg-hotlist backend (keep open)" /MIN "%PY%" -X utf8 "%BACKEND_DIR%\web_app.py"
echo  Waiting for backend to come up...
set "n=0"
:wait
set /a n+=1
timeout /t 1 /nobreak >nul
powershell -NoProfile -Command "try{(Invoke-WebRequest 'http://127.0.0.1:8765/api/state' -UseBasicParsing -TimeoutSec 1)|Out-Null; exit 0}catch{exit 1}" >nul 2>&1
if errorlevel 1 goto wait_more
echo  Backend is up.
goto start_exd
:wait_more
if %n% LSS 15 goto wait
echo  [WARN] backend slow, starting exDesktop anyway.

:start_exd
echo  Starting exDesktop...
start "" "%EXD%"
echo.
echo  ============================================================
echo   exDesktop is starting.
echo   - First run: scan the QR code with your phone
echo     (Telegram - Settings - Devices - Link Desktop Device).
echo   - Then open any group, click the menu (top right)
echo     and choose the Hot Messages item.
echo   - Keep the black backend window open while using it.
echo  ============================================================
echo.
timeout /t 6 /nobreak >nul
exit /b 0

:no_exd
echo  [ERROR] exDesktop not found at:
echo          %EXD%
echo  Extract the portable zip into .\app first.
pause
exit /b 1

:no_py
echo  [ERROR] tg-hotlist venv not found at:
echo          %PY%
pause
exit /b 1
