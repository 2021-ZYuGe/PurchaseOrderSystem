@echo off
cd /d "%~dp0"
title 采购下单系统 - 自检与清理

if not exist "工具\自检与清理.py" (
  echo [错误] 找不到 工具\自检与清理.py，文件夹不完整，请重新解压。
  pause
  exit /b
)

set "PYEXE=%~dp0运行环境\python.exe"
if exist "%PYEXE%" goto RUN

set "PYEXE="
where python >nul 2>&1
if not errorlevel 1 set "PYEXE=python"
if defined PYEXE goto RUN
where py >nul 2>&1
if not errorlevel 1 set "PYEXE=py"
if defined PYEXE goto RUN

echo [错误] 没有找到 Python 运行环境。
echo   如果「运行环境」文件夹还在，说明 python.exe 被被杀毒软件删了。
echo   把整个文件夹压缩成 .zip 再发一次即可。
pause
exit /b

:RUN
"%PYEXE%" "工具\自检与清理.py" %*
echo.
pause
