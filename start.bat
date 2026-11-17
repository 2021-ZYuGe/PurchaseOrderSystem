@echo off
cd /d "%~dp0"
title Purchase Order System
if exist "runtime\pythonw.exe" (
  start "" "runtime\pythonw.exe" -m app
) else (
  start "" pythonw -m app
)
exit /b 0
