@echo off
title FabTwin VPO & History Diagnostic

REM ================================================================
REM FabTwin VPO Model & History Data Diagnostic Tool
REM Checks: Oracle connection, DT_EVENT_RAW data, VPO model config,
REM         Machine-Model mapping, timestamp formats, model files
REM ================================================================

setlocal

set "BASE_DIR=%~dp0"
set "BASE_DIR=%BASE_DIR:~0,-1%"
set "BACKEND_DIR=%BASE_DIR%\backend"
set "PY_EXE=%BACKEND_DIR%\venv\Scripts\python.exe"

REM Load Oracle DB config from env.bat
if exist "%BASE_DIR%\env.bat" (
    call "%BASE_DIR%\env.bat"
) else (
    echo WARNING: env.bat not found, using default DB config
    echo Please create env.bat or set Oracle env vars manually
)

echo ================================================================
echo  FabTwin VPO Model & History Diagnostic Tool
echo ================================================================
echo.
echo DB: %ORACLE_HOST%:%ORACLE_PORT%/%ORACLE_SERVICE% (%ORACLE_USER%)
echo.

if not exist "%PY_EXE%" (
    echo ERROR: Python not found at %PY_EXE%
    echo Please run deploy.bat first to create venv.
    pause
    exit /b 1
)

echo Running diagnostic...
echo.

"%PY_EXE%" "%BASE_DIR%\_check_vpo_and_history.py"

echo.
echo ================================================================
echo  Done. Report saved to: %BASE_DIR%\vpo_history_check_report.txt
echo ================================================================
pause
endlocal
