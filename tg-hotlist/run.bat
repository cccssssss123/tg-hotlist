@echo off
rem tg-hotlist quick launcher (Windows)
rem usage: run.bat chats | run.bat top -g groupname
chcp 65001 >nul
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" tg_hotlist.py %*
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo python not found, please install Python 3.9+ first
        pause
        exit /b 1
    )
    python tg_hotlist.py %*
)
pause
