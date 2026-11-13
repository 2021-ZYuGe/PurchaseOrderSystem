@echo off
cd /d "%~dp0"
echo.
echo   正在为当前文件夹重建「采购合同下单系统」快捷方式...
echo.
"%~dp0运行环境\python.exe" "%~dp0工具\_创建快捷方式.py"
echo.
echo   看到「已生成」就可以了，关掉本窗口，双击快捷方式使用。
echo.
pause
