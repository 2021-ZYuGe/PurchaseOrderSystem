@echo off
cd /d "%~dp0"
title Purchase Order System - maintenance
if exist "runtime\python.exe" (
  "runtime\python.exe" "tools\maintenance.py"
) else (
  python "tools\maintenance.py"
)
exit /b 0
