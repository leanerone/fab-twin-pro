@echo off
setlocal enabledelayedexpansion

REM ================================================================
REM FabTwin Production Start Script
REM 
REM This script starts:
REM   1. Backend (FastAPI on port 8002)
REM   2. Frontend (Vite Preview on port 5173)
REM
REM Prerequisites:
REM   - deploy.bat has been run (venv + node_modules + dist ready)
REM   - env.bat has correct database configuration
REM ================================================================

title FabTwin Start

set "BASE_DIR=%~dp0"
set "BASE_DIR=%BASE_DIR:~0,-1%"
set "BACKEND_DIR=%BASE_DIR%\backend"
set "FRONTEND_DIR=%BASE_DIR%\frontend"

echo ================================================================
echo  FabTwin Production Start
echo ================================================================
echo.

REM ----- Load environment config -----
if exist "%BASE_DIR%\env.bat" (
    call "%BASE_DIR%\env.bat"
) else (
    echo ERROR: env.bat not found
    echo Please create env.bat with your database configuration
    pause
    exit /b 1
)

echo Configuration:
echo   DB_TYPE: %DB_TYPE%
echo   ORACLE_HOST: %ORACLE_HOST%
echo   ORACLE_USER: %ORACLE_USER%
echo   ORACLE_SERVICE: %ORACLE_SERVICE%
echo.

REM ----- Check required files -----
if not exist "%BACKEND_DIR%\venv\Scripts\python.exe" (
    echo ERROR: backend venv not found
    echo Please run deploy.bat first
    pause
    exit /b 1
)

if not exist "%FRONTEND_DIR%\dist\index.html" (
    echo ERROR: frontend dist not found
    echo Please run deploy.bat first
    pause
    exit /b 1
)

REM ----- Check ports -----
netstat -ano | findstr ":8002 " | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo WARNING: Port 8002 already in use
    choice /C YN /M "Continue anyway"
    if errorlevel 2 exit /b 0
)

netstat -ano | findstr ":5173 " | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo WARNING: Port 5173 already in use
    choice /C YN /M "Continue anyway"
    if errorlevel 2 exit /b 0
)

REM ----- Start Backend -----
echo [1/2] Starting backend (FastAPI :8002)...

REM Create a launcher bat to avoid cmd quoting issues
set "BACKEND_LAUNCHER=%BACKEND_DIR%\_run_backend.bat"
(
echo @echo off
echo cd /d "%BACKEND_DIR%"
echo set DB_TYPE=%DB_TYPE%
echo set ORACLE_HOST=%ORACLE_HOST%
echo set ORACLE_PORT=%ORACLE_PORT%
echo set ORACLE_SERVICE=%ORACLE_SERVICE%
echo set ORACLE_USER=%ORACLE_USER%
echo set ORACLE_PASSWORD=%ORACLE_PASSWORD%
echo set ORACLE_DSN_TYPE=%ORACLE_DSN_TYPE%
echo set ORACLE_CLIENT_DIR=%ORACLE_CLIENT_DIR%
echo set SIMULATION_ENABLED=%SIMULATION_ENABLED%
echo set DB_POLLER_ENABLED=%DB_POLLER_ENABLED%
echo set NO_PROXY=*
echo set no_proxy=*
echo set HTTP_PROXY=
echo set HTTPS_PROXY=
echo echo === Backend Config ===
echo echo DB_TYPE=%DB_TYPE%
echo echo ORACLE_HOST=%ORACLE_HOST%
echo echo ORACLE_USER=%ORACLE_USER%
echo echo ORACLE_CLIENT_DIR=%ORACLE_CLIENT_DIR%
echo echo ======================
echo venv\Scripts\python.exe main.py
) > "%BACKEND_LAUNCHER%"

start "FabTwin Backend" cmd /k "%BACKEND_LAUNCHER%"

echo   Backend starting... (check new window for logs)
timeout /t 3 /nobreak >nul

REM ----- Start Frontend -----
echo [2/2] Starting frontend (Vite Preview :5173)...

cd /d "%FRONTEND_DIR%"
set "NO_PROXY=*"
set "no_proxy="

if exist "node_modules\.bin\vite.cmd" (
    start "FabTwin Frontend" cmd /k "cd /d "%FRONTEND_DIR%" && set NO_PROXY=* && node_modules\.bin\vite.cmd preview --port 5173 --host"
) else (
    start "FabTwin Frontend" cmd /k "cd /d "%FRONTEND_DIR%" && set NO_PROXY=* && npx vite preview --port 5173 --host"
)

echo   Frontend starting...
echo.

REM ----- Done -----
echo ================================================================
echo  Services Started!
echo ================================================================
echo.
echo  Frontend:  http://localhost:5173
echo  Backend:   http://localhost:8002
echo  API docs:  http://localhost:8002/docs
echo  Health:    http://localhost:8002/health
echo.
echo  Close the windows to stop the services.
echo.
pause
endlocal