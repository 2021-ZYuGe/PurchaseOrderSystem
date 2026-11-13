@echo off
cd /d "%~dp0"
title 关闭采购下单系统

if not exist "工具\退出系统.py" (
  echo [错误] 找不到 工具\退出系统.py，文件夹不完整。
  pause
  exit /b
)

if exist "运行环境\pythonw.exe" (
  start "" "运行环境\pythonw.exe" "工具\退出系统.py"
) else (
  where pythonw >nul 2>&1
  if not errorlevel 1 (
    start "" pythonw "工具\退出系统.py"
  ) else (
    where python >nul 2>&1
    if not errorlevel 1 (
      python "工具\退出系统.py"
    ) else (
      echo [错误] 没有找到 Python 运行环境。
      pause
    )
  )
)
