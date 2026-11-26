@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0" || exit /b 1

if exist ".market-radar\python\python.exe" goto run_local
for /f "delims=" %%I in ('py -3 -c "import sys; print(sys.version_info[0])" 2^>nul') do if "%%I"=="3" goto run_py
for /f "delims=" %%I in ('python -c "import sys; print(sys.version_info[0])" 2^>nul') do if "%%I"=="3" goto run_python

echo 未找到可运行的 Python 3。请安装 Python 后重新打开向导。
pause
exit /b 1

:run_local
".market-radar\python\python.exe" run_radar.py
goto finish

:run_py
py -3 run_radar.py
goto finish

:run_python
python run_radar.py

:finish
set "RADAR_STATUS=%ERRORLEVEL%"
if not "%RADAR_STATUS%"=="0" echo 向导启动失败，请查看上方错误。
pause
exit /b %RADAR_STATUS%
