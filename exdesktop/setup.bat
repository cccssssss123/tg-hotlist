@echo off
rem tg-hotlist one-click setup (ASCII-only on purpose)
chcp 65001 >nul
title tg-hotlist setup
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
echo.
pause
