@echo off
cd /d "%~dp0.."
title 生成我的采购下单数据

echo ============================================================
echo         采购下单系统  -  用自己的合同数据生成
echo ============================================================
echo.
echo  使用前请确认：
echo    你已从 WorkBuddy 接入企微易快报，导出【自己的合同附件文件夹】（.docx 文件）
echo.
echo  本工具会读取这些合同，自动生成属于你的：
echo    产品库 + 规格 + 图片 + 供应商 + 主合同日期
echo.
echo  ------------------------------------------------------------
echo  提示：生成的系统只含你自己的数据，不影响他人。
echo  ------------------------------------------------------------
echo.
if not "%~1"=="" goto SKIP_WAIT
echo  按任意键开始…
pause >nul
:SKIP_WAIT

set "PYEXE=%~dp0..\运行环境\python.exe"
if exist "%PYEXE%" goto GOT_PY

set "PYEXE="
where python >nul 2>&1
if not errorlevel 1 set "PYEXE=python"
if defined PYEXE goto GOT_PY
where py >nul 2>&1
if not errorlevel 1 set "PYEXE=py"
if defined PYEXE goto GOT_PY
goto ERR_PY

:GOT_PY
"%PYEXE%" -c "import docx" >nul 2>&1
if not errorlevel 1 goto RUN

echo.
echo 正在准备所需组件（首次约需 1 分钟）…
"%PYEXE%" -m pip install python-docx -q --disable-pip-version-check >nul 2>&1
"%PYEXE%" -c "import docx" >nul 2>&1
if not errorlevel 1 goto RUN
goto ERR_DOCX

:RUN
cls
if "%~1"=="" goto RUN_INPUT
"%PYEXE%" "%~dp0_工具_生成数据库.py" "%~1"
goto RUN_DONE

:RUN_INPUT
"%PYEXE%" "%~dp0_工具_生成数据库.py"

:RUN_DONE
echo.
echo ------------------------------------------------------------
echo  生成结束。回到上一层文件夹，双击【启动网页版.bat】即可开始使用。
echo ------------------------------------------------------------
pause
exit /b

:ERR_PY
echo.
echo [错误] 没找到 Python 运行环境。
echo.
if exist "运行环境" (
  echo   检测到"运行环境"文件夹存在，但里面的 python.exe 不见了。
  echo   这种情况通常是：用微信 / QQ 直接发送文件夹时，
  echo   .exe 文件被自动过滤掉了。
  echo   解决办法：把整个文件夹压缩成 .zip 再发送，对方解压后运行。
) else (
  echo   请把"运行环境"文件夹一起拷贝过来，
  echo   或者安装 Python 并勾选 "Add Python to PATH"。
)
echo.
pause
exit /b

:ERR_DOCX
echo.
echo [错误] 缺少读取 Word 的组件（python-docx）。
echo   如果你用的是本文件夹内置的运行环境，说明文件已损坏，
echo   请重新解压分享包。
echo   如果你用的是自己安装的 Python，请先执行：
echo       %PYEXE% -m pip install python-docx
echo.
pause
exit /b
