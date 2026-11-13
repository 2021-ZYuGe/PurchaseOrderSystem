@echo off
cd /d "%~dp0"
title 采购下单系统

echo ============================================
echo            采购下单系统  启动中
echo ============================================
echo.

if not exist "web\index.html" goto ERR_FILES

rem 2026-11-04：原来的 python -m http.server 只能浏览网页，没有生成合同接口。
rem 改为启动正式服务（工具\打开系统_静默.py），生成合同/导出收集表才可用。
if exist "%~dp0运行环境\pythonw.exe" (
  start "" "%~dp0运行环境\pythonw.exe" "%~dp0工具\打开系统_静默.py"
) else (
  start "" pythonw "%~dp0工具\打开系统_静默.py"
)

echo   已启动，浏览器会自动打开。
echo   如果没反应，请稍等几秒，或手动打开 http://127.0.0.1:8899/index.html
echo   关闭系统：双击「关闭系统.bat」
echo.
timeout /t 3 /nobreak >nul
exit /b

:ERR_FILES
echo [错误] 找不到网页文件 web\index.html，文件夹不完整，请重新解压。
pause
exit /b
