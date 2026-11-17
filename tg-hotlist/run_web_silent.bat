@echo off
rem tg-hotlist silent launcher - no black window (ASCII-only on purpose)
chcp 65001 >nul
cd /d "%~dp0"

set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

powershell -NoProfile -Command "$p = '%PY%'; $s = New-Object -ComObject WScript.Shell; $s.Run('\"' + $p + '\" -X utf8 \"%~dp0web_app.py\"', 0, $false)"

set /a n=0
:wait
set /a n+=1
timeout /t 1 /nobreak >nul
powershell -NoProfile -Command "try{(Invoke-WebRequest 'http://127.0.0.1:8765/api/state' -UseBasicParsing -TimeoutSec 1)|Out-Null; exit 0}catch{exit 1}" >nul 2>&1
if %errorlevel% equ 0 goto ready
if %n% LSS 10 goto wait
:ready
start "" "http://127.0.0.1:8765"
