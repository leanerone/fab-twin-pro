@echo off
title FabTwin Deploy

REM ================================================================
REM FabTwin One-Click Deployment Script
REM Usage: Deploy frontend and backend services on intranet prod server
REM Flow: check env -> install deps -> init DB -> build frontend -> start
REM
REM IMPORTANT: This script uses English only to avoid UTF-8/GBK issues
REM            on Windows Server. Do not add Chinese comments.
REM ================================================================

setlocal enabledelayedexpansion

set "BASE_DIR=%~dp0"
set "BASE_DIR=%BASE_DIR:~0,-1%"
set "BACKEND_DIR=%BASE_DIR%\backend"
set "FRONTEND_DIR=%BASE_DIR%\frontend"

echo ================================================================
echo          FabTwin Deployment
echo ================================================================
echo Deploy dir: %BASE_DIR%
echo.

REM ---------- Production env vars ----------
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

echo [1/5] Checking environment...
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found, please install Python 3.10+ first
    pause
    exit /b 1
)

node --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Node.js not found, please install Node.js 16+ first
    pause
    exit /b 1
)

echo OK: Python and Node.js ready
echo.

REM ---------- [2/5] Backend deps ----------
echo [2/5] Deploying backend...
echo.

if not exist "%BACKEND_DIR%\venv" (
    echo Creating Python venv...
    cd /d "%BACKEND_DIR%"
    python -m venv venv
    if errorlevel 1 (
        echo ERROR: venv creation failed
        pause
        exit /b 1
    )
)

echo Installing backend deps...
cd /d "%BACKEND_DIR%"

if exist "wheels" (
    echo INFO: wheels dir found, using offline install
    venv\Scripts\pip.exe install --no-index --find-links wheels -r requirements.txt -q
) else (
    venv\Scripts\pip.exe install -r requirements.txt -q
)

if errorlevel 1 (
    echo WARNING: pip install may have partial failures, continuing...
)

REM ---------- [3/5] Database init ----------
echo.
echo [3/5] Initializing database...
echo.

REM Build connection string
if not defined ORACLE_HOST set "ORACLE_HOST=localhost"
if not defined ORACLE_PORT set "ORACLE_PORT=1521"
if not defined ORACLE_SERVICE set "ORACLE_SERVICE=ORCLPDB"
if not defined ORACLE_USER set "ORACLE_USER=fabtwin"
if not defined ORACLE_PASSWORD set "ORACLE_PASSWORD=fabtwin"

set "CONN_STR=%ORACLE_USER%/%ORACLE_PASSWORD%@%ORACLE_HOST%:%ORACLE_PORT%/%ORACLE_SERVICE%"

where sqlplus >nul 2>&1
if errorlevel 1 (
    echo WARNING: sqlplus not found, skipping SQL script init
    echo Will use ORM create_all to create empty tables (no base data)
    echo.
    echo For full init with base data, ask DBA team to run:
    echo   sql\init_oracle_db.sql  on the Oracle server
    echo.
    venv\Scripts\python.exe -c "from database import init_db; init_db(); print('ORM tables created')"
    if errorlevel 1 (
        echo ERROR: ORM init failed
        pause
        exit /b 1
    )
) else (
    if exist "%BASE_DIR%\sql\init_oracle_db.sql" (
        echo INFO: Running sql\init_oracle_db.sql
        echo INFO: Connecting %ORACLE_HOST%:%ORACLE_PORT%/%ORACLE_SERVICE% as %ORACLE_USER%
        sqlplus -S "%CONN_STR%" @%BASE_DIR%\sql\init_oracle_db.sql > "%BASE_DIR%\init_db.log" 2>&1
        if errorlevel 1 (
            echo WARNING: SQL script may have errors, check init_db.log
            echo Last 20 lines:
            powershell -Command "Get-Content %BASE_DIR%\init_db.log -Tail 20" 2>nul
        ) else (
            echo OK: Database initialized
        )
    ) else (
        echo WARNING: sql\init_oracle_db.sql not found, using ORM create_all
        venv\Scripts\python.exe -c "from database import init_db; init_db(); print('ORM tables created')"
    )
)

REM ---------- [4/5] Frontend build ----------
echo.
echo [4/5] Deploying frontend...
echo.

cd /d "%FRONTEND_DIR%"

if exist "dist\index.html" (
    echo INFO: dist exists, skipping build
) else (
    if not exist "node_modules" (
        echo Installing frontend deps...
        cmd /c "npm install -q"
        if errorlevel 1 (
            echo WARNING: npm install failed, check node_modules
        )
    )

    echo Building frontend...
    if exist "node_modules\.bin\vite.cmd" (
        cmd /c "node_modules\.bin\vite.cmd build"
    ) else (
        cmd /c "npm run build"
    )
    if errorlevel 1 (
        echo ERROR: Frontend build failed
        pause
        exit /b 1
    )
)

REM ---------- [5/5] Start services ----------
echo.
echo [5/5] Starting services...
echo.

netstat -ano | findstr ":8002 " | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo WARNING: port 8002 in use, backend may be running
)

netstat -ano | findstr ":5173 " | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo WARNING: port 5173 in use, frontend may be running
)

echo.
echo ================================================================
echo  Service Info
echo ================================================================
echo  Frontend:  http://localhost:5173
echo  Backend:   http://localhost:8002
echo  API docs:  http://localhost:8002/docs
echo  Health:    http://localhost:8002/health
echo ================================================================
echo.
echo Press any key to start services (close windows to stop)...
pause >nul

echo Starting backend...
start "FabTwin Backend" cmd /k "cd /d %BACKEND_DIR% && set DB_TYPE=oracle && set SIMULATION_ENABLED=False && set DB_POLLER_ENABLED=True && venv\Scripts\python.exe main.py"

echo Waiting for backend to start (5 sec)...
timeout /t 5 /nobreak >nul

echo Starting frontend (vite preview production mode)...
cd /d "%FRONTEND_DIR%"
if exist "node_modules\.bin\vite.cmd" (
    start "FabTwin Frontend" cmd /k "cd /d %FRONTEND_DIR% && node_modules\.bin\vite.cmd preview --port 5173 --host"
) else (
    echo WARNING: vite.cmd not found, trying npx
    start "FabTwin Frontend" cmd /k "cd /d %FRONTEND_DIR% && npx vite preview --port 5173 --host"
)

echo.
echo ================================================================
echo  Services started!
echo ================================================================
echo  Open browser: http://localhost:5173
echo.
echo  Login: NT auto-login or admin/admin123
echo ================================================================
echo.
pause
endlocal
