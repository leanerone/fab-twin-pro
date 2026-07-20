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

REM Production env vars
set "DB_TYPE=oracle"
set "SIMULATION_ENABLED=False"
set "DB_POLLER_ENABLED=True"

REM Uncomment and modify if non-default Oracle config
REM set "ORACLE_HOST=192.168.x.x"
REM set "ORACLE_PORT=1521"
REM set "ORACLE_SERVICE=ORCLPDB"
REM set "ORACLE_USER=fabtwin"
REM set "ORACLE_PASSWORD=fabtwin"

REM For Oracle 10g/11g: set ORACLE_CLIENT_DIR to Instant Client path
REM set "ORACLE_CLIENT_DIR=C:\oracle\instantclient_19_x"

echo [1/2] Starting backend (FastAPI :8002)...
start "FabTwin Backend" cmd /k "cd /d %BACKEND_DIR% && set DB_TYPE=oracle && set SIMULATION_ENABLED=False && set DB_POLLER_ENABLED=True && venv\Scripts\python.exe main.py"

echo Waiting for backend to start (5 sec)...
timeout /t 5 /nobreak >nul

echo [2/2] Starting frontend (Vite Preview :5173)...
cd /d "%FRONTEND_DIR%"
if exist "node_modules\.bin\vite.cmd" (
    start "FabTwin Frontend" cmd /k "cd /d %FRONTEND_DIR% && node_modules\.bin\vite.cmd preview --port 5173 --host"
) else (
    echo WARNING: vite.cmd not found, using npx
    start "FabTwin Frontend" cmd /k "cd /d %FRONTEND_DIR% && npx vite preview --port 5173 --host"
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
