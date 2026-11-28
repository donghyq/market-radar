@echo off
setlocal
chcp 65001 >nul
pushd "%~dp0" || exit /b 1
set "PYTHONUTF8=1"

if exist ".market-radar\python\python.exe" (
    ".market-radar\python\python.exe" -c "import sys; raise SystemExit(int(sys.version_info < (3, 10)))" >nul 2>&1
    if not errorlevel 1 goto run_local
)
for /f "delims=" %%I in ('py -3 -c "import sys; print(int(sys.version_info >= (3, 10)))" 2^>nul') do if "%%I"=="1" goto run_py
for /f "delims=" %%I in ('python -c "import sys; print(int(sys.version_info >= (3, 10)))" 2^>nul') do if "%%I"=="1" goto run_python

echo 未找到可运行的 Python 3.10 或更新版本。请安装 Python 后重新打开向导。
popd
if "%~1"=="" pause
exit /b 1

:run_local
".market-radar\python\python.exe" -X utf8 run_radar.py %*
goto finish

:run_py
py -3 -X utf8 run_radar.py %*
goto finish

:run_python
python -X utf8 run_radar.py %*

:finish
set "RADAR_STATUS=%ERRORLEVEL%"
if not "%RADAR_STATUS%"=="0" echo 执行失败，请查看上方错误。
popd
if "%~1"=="" pause
exit /b %RADAR_STATUS%
