@echo off
title FabTwin Production Status Check

REM ================================================================
REM FabTwin Production Database Status Checker
REM READ ONLY - does NOT modify any data
REM Checks: Machine, MachineModelConfig, DT_EVENT_RAW, model mapping
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
echo  FabTwin Production Database Status Check
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

"%PY_EXE%" "%BASE_DIR%\_check_production.py"

pause
endlocal
