@echo off
chcp 65001 > nul
setlocal
set "ROOT=%~dp0"
set "PY=python"
set "LOGDIR=%ROOT%logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

echo =======================================
echo    LOF Fund Arbitrage System
echo =======================================
echo.

where %PY% >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [Error] Python not found!
    pause > nul
    exit /b 1
)

echo [System] Checking database...

echo [Cleanup] Terminating Python processes...
taskkill /f /im python.exe > nul 2>&1

set PYTHONIOENCODING=utf-8

echo [0/6] Skipping manual 011 update (handled intelligently by LOF03)...
echo [1/6] Skipping manual 012 static valuation (handled intelligently by LOF03)...

echo [2/6] Starting admin panel (port 5002)...
start "LOF Admin (5002)" /D "%ROOT%" cmd /k ""%PY%" -X utf8 LOF01_admin_launcher.py"

echo [3/6] Starting data service (port 5000)...
start "LOF Backend (5000)" /D "%ROOT%" cmd /k ""%PY%" -X utf8 LOF02_fetch_trade_data.py"

echo Waiting for initialization (8 sec)...
timeout /t 8 > nul

echo [4/6] Generating report...
pushd "%ROOT%"
"%PY%" -X utf8 LOF03_generate_monitor_html.py > "%LOGDIR%\html_generate.log" 2>&1
if errorlevel 1 (
    echo [Error] 03 failed!
    pause > nul
    exit /b 1
)
popd
echo Report generated.

echo [5/6] Opening browser...
start "" "http://localhost:5000/"

echo.
echo =======================================
echo System started successfully!
echo Monitor: http://localhost:5000/
echo Admin: http://localhost:5002/
echo =======================================
pause > nul
endlocal