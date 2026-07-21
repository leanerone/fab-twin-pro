@echo off
title FabTwin Prod Start

REM ================================================================
REM FabTwin Production Start Script
REM Usage: Start frontend and backend services on prod server
REM Prereq: deploy.bat has been run (venv + node_modules + dist ready)
REM
REM IMPORTANT: English only to avoid encoding issues on Windows Server
REM ================================================================

setlocal
set "BASE_DIR=%~dp0"
set "BASE_DIR=%BASE_DIR:~0,-1%"
set "BACKEND_DIR=%BASE_DIR%\backend"
set "FRONTEND_DIR=%BASE_DIR%\frontend"

echo ================================================================
echo  FabTwin Production Start
echo ================================================================
echo.

REM Check required files
if not exist "%BACKEND_DIR%\venv\Scripts\python.exe" (
    echo ERROR: backend venv not found, please run deploy.bat first
    pause
    exit /b 1
)

if not exist "%FRONTEND_DIR%\dist\index.html" (
    echo ERROR: frontend dist not found, please run deploy.bat first
    pause
    exit /b 1
)

REM Check port usage
netstat -ano | findstr ":8002 " | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo WARNING: port 8002 in use, backend may be running
    choice /C YN /M "Continue starting backend (may fail)"
    if errorlevel 2 exit /b 0
)

netstat -ano | findstr ":5173 " | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo WARNING: port 5173 in use, frontend may be running
    choice /C YN /M "Continue starting frontend (may fail)"
    if errorlevel 2 exit /b 0
)

REM ---------- Load env.bat if exists ----------
if exist "%BASE_DIR%\env.bat" (
    call "%BASE_DIR%\env.bat"
    echo [INFO] Loaded DB config from env.bat
) else (
    echo [INFO] env.bat not found, using inline defaults
)

REM Production env vars
if not defined DB_TYPE set "DB_TYPE=oracle"
if not defined SIMULATION_ENABLED set "SIMULATION_ENABLED=False"
if not defined DB_POLLER_ENABLED set "DB_POLLER_ENABLED=True"

REM 关键：绕过 HJTC Proxy 系统代理拦截
set "NO_PROXY=*"
set "no_proxy=*"
set "HTTP_PROXY="
set "HTTPS_PROXY="
set "http_proxy="
set "https_proxy="

REM Fallback defaults if still not set
if not defined ORACLE_HOST set "ORACLE_HOST=localhost"
if not defined ORACLE_PORT set "ORACLE_PORT=1521"
if not defined ORACLE_SERVICE set "ORACLE_SERVICE=ORCLPDB"
if not defined ORACLE_USER set "ORACLE_USER=fabtwin"
if not defined ORACLE_PASSWORD set "ORACLE_PASSWORD=fabtwin"
if not defined ORACLE_DSN_TYPE set "ORACLE_DSN_TYPE=service_name"

echo [1/2] Starting backend (FastAPI :8002)...
start "FabTwin Backend" cmd /k "cd /d %BACKEND_DIR% && set DB_TYPE=oracle && set SIMULATION_ENABLED=False && set DB_POLLER_ENABLED=True && set ORACLE_HOST=%ORACLE_HOST% && set ORACLE_PORT=%ORACLE_PORT% && set ORACLE_SERVICE=%ORACLE_SERVICE% && set ORACLE_USER=%ORACLE_USER% && set ORACLE_PASSWORD=%ORACLE_PASSWORD% && set ORACLE_DSN_TYPE=%ORACLE_DSN_TYPE% && set ORACLE_CLIENT_DIR=%ORACLE_CLIENT_DIR% && set NO_PROXY=* && set no_proxy=* && set HTTP_PROXY= && set HTTPS_PROXY= && venv\Scripts\python.exe main.py"

echo Waiting for backend to start (5 sec)...
timeout /t 5 /nobreak >nul

echo [2/2] Starting frontend (Vite Preview :5173)...
cd /d "%FRONTEND_DIR%"
set "NO_PROXY=*"
set "no_proxy=*"
if exist "node_modules\.bin\vite.cmd" (
    start "FabTwin Frontend" cmd /k "cd /d %FRONTEND_DIR% && set NO_PROXY=* && set no_proxy=* && set HTTP_PROXY= && set HTTPS_PROXY= && node_modules\.bin\vite.cmd preview --port 5173 --host"
) else (
    echo WARNING: vite.cmd not found, using npx
    start "FabTwin Frontend" cmd /k "cd /d %FRONTEND_DIR% && set NO_PROXY=* && set no_proxy=* && set HTTP_PROXY= && set HTTPS_PROXY= && npx vite preview --port 5173 --host"
)

echo.
echo ================================================================
echo  Services started!
echo ================================================================
echo  Frontend:  http://localhost:5173
echo  Backend:   http://localhost:8002
echo  API docs:  http://localhost:8002/docs
echo  Health:    http://localhost:8002/health
echo ================================================================
echo.
echo Close the corresponding window to stop the service
echo.
pause
endlocal
