@echo off
cd /d "%~dp0.."
set "R=%CD%\诊断报告.txt"

echo 正在检查运行环境，请稍等……

set "F1=缺失"
if exist "web\index.html" set "F1=存在"
set "F2=缺失"
if exist "web\app.js" set "F2=存在"
set "F3=缺失"
if exist "web\data.js" set "F3=存在"
set "F4=缺失"
if exist "工具\_工具_生成数据库.py" set "F4=存在"
set "F5=缺失"
if exist "运行环境\python.exe" set "F5=存在"
set "F6=缺失"
if exist "运行环境" set "F6=存在"
set "F7=缺失"
if exist "启动网页版.bat" set "F7=存在"

> "%R%" echo 采购下单系统 - 诊断报告
>> "%R%" echo 生成时间: %date% %time%
>> "%R%" echo ============================================
>> "%R%" echo [1] 电脑信息
>> "%R%" echo 计算机名: %COMPUTERNAME%
>> "%R%" echo 用户名: %USERNAME%
>> "%R%" echo 当前文件夹: %CD%
>> "%R%" ver
>> "%R%" echo.
>> "%R%" echo [2] 关键文件检查
>> "%R%" echo   web\index.html          : %F1%
>> "%R%" echo   web\app.js              : %F2%
>> "%R%" echo   web\data.js             : %F3%
>> "%R%" echo   启动网页版.bat          : %F7%
>> "%R%" echo   工具\_工具_生成数据库.py : %F4%
>> "%R%" echo   运行环境 文件夹         : %F6%
>> "%R%" echo   运行环境\python.exe     : %F5%
>> "%R%" echo.
>> "%R%" echo [3] 内置运行环境自检
if exist "%~dp0..\运行环境\python.exe" (
  "%~dp0..\运行环境\python.exe" -V >> "%R%" 2>&1
  "%~dp0..\运行环境\python.exe" -c "import docx; print('  python-docx 可用')" >> "%R%" 2>&1
  "%~dp0..\运行环境\python.exe" -c "import http.server; print('  http.server 可用')" >> "%R%" 2>&1
) else (
  >> "%R%" echo   内置运行环境不存在（python.exe 缺失）
)
>> "%R%" echo.
>> "%R%" echo [4] 系统 Python 检查
where python >> "%R%" 2>&1
where py >> "%R%" 2>&1
>> "%R%" echo.
>> "%R%" echo [5] 端口 8899 占用情况
netstat -ano | findstr ":8899 " >> "%R%" 2>&1
>> "%R%" echo.
>> "%R%" echo [6] 本文件夹内容
dir /b >> "%R%" 2>&1
>> "%R%" echo.
>> "%R%" echo [7] web 文件夹内容
dir /b web >> "%R%" 2>&1
>> "%R%" echo.
>> "%R%" echo [8] 图片文件夹（只显示前 15 个）
dir /b "web\图片" >> "%R%" 2>&1
>> "%R%" echo.
>> "%R%" echo ================== 报告结束 ==================
>> "%R%" echo 请把上一层文件夹里的【诊断报告.txt】发给小简。

echo.
echo 检查完成，诊断报告已生成在上一层文件夹：诊断报告.txt
echo 请把这个文件发给小简，就能定位问题。
echo.
pause
