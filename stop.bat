@echo off
cd /d "%~dp0"
title Purchase Order System - stop
if exist "runtime\python.exe" (
  "runtime\python.exe" "tools\stop.py"
) else (
  python "tools\stop.py"
)
timeout /t 2 >nul
exit /b 0
