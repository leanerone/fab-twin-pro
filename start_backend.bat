@echo off
setlocal enabledelayedexpansion

REM ================================================================
REM FabTwin Backend Starter - Robust version
REM Writes env vars to a temp file to avoid batch quoting issues
REM ================================================================

set "BASE_DIR=%~dp0"
set "BACKEND_DIR=%BASE_DIR%backend"

echo ================================================================
echo  FabTwin Backend Starter
echo ================================================================
echo.

REM Check venv
if not exist "%BACKEND_DIR%\venv\Scripts\python.exe" (
    echo ERROR: backend venv not found
    pause
    exit /b 1
)

REM Load env.bat
if exist "%BASE_DIR%env.bat" (
    call "%BASE_DIR%env.bat"
    echo [INFO] Loaded env.bat
) else (
    echo WARNING: env.bat not found
)

REM Show what we will use
echo.
echo === Effective DB Config ===
echo DB_TYPE          = !DB_TYPE!
echo ORACLE_HOST      = !ORACLE_HOST!
echo ORACLE_PORT      = !ORACLE_PORT!
echo ORACLE_SERVICE   = !ORACLE_SERVICE!
echo ORACLE_USER      = !ORACLE_USER!
echo ORACLE_DSN_TYPE  = !ORACLE_DSN_TYPE!
echo ORACLE_CLIENT_DIR= !ORACLE_CLIENT_DIR!
echo.

if not defined DB_TYPE set "DB_TYPE=oracle"
if not defined SIMULATION_ENABLED set "SIMULATION_ENABLED=False"
if not defined DB_POLLER_ENABLED set "DB_POLLER_ENABLED=True"

REM Bypass system proxy (HJTC)
set "NO_PROXY=*"
set "no_proxy=*"
set "HTTP_PROXY="
set "HTTPS_PROXY="
set "http_proxy="
set "https_proxy="

echo === Starting backend (FastAPI :8002) ===
echo  Watch the new window for logs.
echo  Press Ctrl+C in the new window to stop the backend.
echo.

REM Create a launcher bat in backend dir (avoids TEMP path quoting issues)
set "LAUNCHER=%BACKEND_DIR%\_run_backend.bat"
(
  echo @echo off
  echo chcp 65001 ^>nul
  echo cd /d "%BACKEND_DIR%"
  echo set DB_TYPE=!DB_TYPE!
  echo set SIMULATION_ENABLED=!SIMULATION_ENABLED!
  echo set DB_POLLER_ENABLED=!DB_POLLER_ENABLED!
  echo set ORACLE_HOST=!ORACLE_HOST!
  echo set ORACLE_PORT=!ORACLE_PORT!
  echo set ORACLE_SERVICE=!ORACLE_SERVICE!
  echo set ORACLE_USER=!ORACLE_USER!
  echo set ORACLE_PASSWORD=!ORACLE_PASSWORD!
  echo set ORACLE_DSN_TYPE=!ORACLE_DSN_TYPE!
  echo set ORACLE_CLIENT_DIR=!ORACLE_CLIENT_DIR!
  echo set NO_PROXY=*
  echo set no_proxy=*
  echo set HTTP_PROXY=
  echo set HTTPS_PROXY=
  echo echo === Effective Config ===
  echo echo DB_TYPE=!DB_TYPE!
  echo echo ORACLE_HOST=!ORACLE_HOST!
  echo echo ORACLE_USER=!ORACLE_USER!
  echo echo ORACLE_SERVICE=!ORACLE_SERVICE!
  echo echo ORACLE_CLIENT_DIR=!ORACLE_CLIENT_DIR!
  echo echo ===========================
  echo venv\Scripts\python.exe main.py
) > "%LAUNCHER%"

echo [INFO] Created launcher: %LAUNCHER%
start "FabTwin Backend" cmd /k "%LAUNCHER%"

echo.
echo Backend started in new window.
echo Close that window to stop the backend.
echo.
pause
endlocal
