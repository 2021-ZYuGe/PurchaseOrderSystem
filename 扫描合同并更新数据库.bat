@echo off
chcp 936 >nul
cd /d "%~dp0"
title 扫描合同并更新数据库

set "PYEXE=%~dp0运行环境\python.exe"
if exist "%PYEXE%" goto RUN

where python >nul 2>&1
if not errorlevel 1 (
  set "PYEXE=python"
  goto RUN
)

echo.
echo [错误] 找不到 运行环境\python.exe
echo        请确认项目文件夹完整，或安装 Python 后重试。
echo.
pause
exit /b 1

:RUN
if "%~1"=="" (
  "%PYEXE%" "%~dp0工具\合并新合同.py"
) else (
  "%PYEXE%" "%~dp0工具\合并新合同.py" "%~1"
)
