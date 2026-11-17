@echo off
rem tg-hotlist stop service (ASCII-only on purpose)
chcp 65001 >nul
echo Stopping tg-hotlist local server...
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*web_app.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; \"Stopped PID $($_.ProcessId)\" }"
echo Done.
timeout /t 2 /nobreak >nul
