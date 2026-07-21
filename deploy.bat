@echo off
setlocal enabledelayedexpansion

REM ================================================================
REM FabTwin One-Click Deployment Script
REM 
REM This script does:
REM   1. Check prerequisites (Python 3.11+, Node.js 18+)
REM   2. Load environment config from env.bat
REM   3. Create Python venv and install dependencies
REM   4. Install frontend dependencies
REM   5. Build frontend (npm run build)
REM   6. Verify database connection
REM
REM Prerequisites:
REM   - Python 3.11+ in PATH
REM   - Node.js 18+ in PATH
REM   - Oracle Client 19c+ (for Oracle 10g/11g connection)
REM ================================================================

title FabTwin Deploy

set "BASE_DIR=%~dp0"
set "BASE_DIR=%BASE_DIR:~0,-1%"
set "BACKEND_DIR=%BASE_DIR%\backend"
set "FRONTEND_DIR=%BASE_DIR%\frontend"

echo ================================================================
echo  FabTwin Deployment
echo ================================================================
echo.

REM ----- Step 1: Check prerequisites -----
echo [1/6] Checking prerequisites...

where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH
    pause
    exit /b 1
)
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VER=%%i
echo   Python: %PYTHON_VER%

where node >nul 2>&1
if errorlevel 1 (
    echo ERROR: Node.js not found in PATH
    pause
    exit /b 1
)
for /f "tokens=1" %%i in ('node --version 2^>^&1') do set NODE_VER=%%i
echo   Node.js: %NODE_VER%

echo.

REM ----- Step 2: Load env.bat -----
echo [2/6] Loading environment config...
if exist "%BASE_DIR%\env.bat" (
    call "%BASE_DIR%\env.bat"
    echo   DB_TYPE: !DB_TYPE!
    echo   ORACLE_HOST: !ORACLE_HOST!
    echo   ORACLE_USER: !ORACLE_USER!
    echo   ORACLE_SERVICE: !ORACLE_SERVICE!
    echo   ORACLE_CLIENT_DIR: !ORACLE_CLIENT_DIR!
) else (
    echo   WARNING: env.bat not found, using defaults
    set "DB_TYPE=oracle"
)
echo.

REM ----- Step 3: Backend venv and dependencies -----
echo [3/6] Setting up backend...
cd /d "%BACKEND_DIR%"

if not exist "venv" (
    echo   Creating Python venv...
    python -m venv venv
    if errorlevel 1 (
        echo ERROR: Failed to create venv
        pause
        exit /b 1
    )
)

echo   Installing Python dependencies...
call venv\Scripts\activate
python -m pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: pip install failed
    pause
    exit /b 1
)
call deactivate
echo   Backend ready.
echo.

REM ----- Step 4: Frontend dependencies -----
echo [4/6] Setting up frontend...
cd /d "%FRONTEND_DIR%"

if not exist "node_modules" (
    echo   Installing npm dependencies...
    call npm install
    if errorlevel 1 (
        echo ERROR: npm install failed
        pause
        exit /b 1
    )
) else (
    echo   node_modules exists, skipping npm install
)
echo.

REM ----- Step 5: Build frontend -----
echo [5/6] Building frontend...
call npm run build
if errorlevel 1 (
    echo ERROR: npm run build failed
    pause
    exit /b 1
)
if not exist "dist\index.html" (
    echo ERROR: dist\index.html not found after build
    pause
    exit /b 1
)
echo   Frontend built successfully.
echo.

REM ----- Step 6: Verify database connection -----
echo [6/6] Testing database connection...
cd /d "%BASE_DIR%"

REM Create a temp test script
set "TEST_SCRIPT=%BACKEND_DIR%\_test_db_conn.py"
(
echo import os
echo os.environ['DB_TYPE'] = '!DB_TYPE!'
echo os.environ['ORACLE_HOST'] = '!ORACLE_HOST!'
echo os.environ['ORACLE_PORT'] = '!ORACLE_PORT!'
echo os.environ['ORACLE_SERVICE'] = '!ORACLE_SERVICE!'
echo os.environ['ORACLE_USER'] = '!ORACLE_USER!'
echo os.environ['ORACLE_PASSWORD'] = '!ORACLE_PASSWORD!'
echo os.environ['ORACLE_DSN_TYPE'] = '!ORACLE_DSN_TYPE!'
echo os.environ['ORACLE_CLIENT_DIR'] = '!ORACLE_CLIENT_DIR!'
echo from sqlalchemy import text
echo from database import SessionLocal, engine
echo print(f'Engine: {engine.url}')
echo db = SessionLocal^(^)
echo result = db.execute^(text^('SELECT 1 FROM DUAL'^)^)
echo print^('Database connection: OK'^)
echo db.close^(^)
) > "%TEST_SCRIPT%"

call "%BACKEND_DIR%\venv\Scripts\python.exe" "%TEST_SCRIPT%"
if errorlevel 1 (
    echo.
    echo WARNING: Database connection test failed
    echo Please check:
    echo   1. Oracle Client is installed and ORACLE_CLIENT_DIR is correct
    echo   2. Database credentials in env.bat are correct
    echo   3. Network connectivity to !ORACLE_HOST!:!ORACLE_PORT!
    echo.
    echo You can still start the app, but database features may not work.
) else (
    echo   Database connection: OK
)
del "%TEST_SCRIPT%" 2>nul
echo.

REM ----- Done -----
echo ================================================================
echo  Deployment Complete!
echo ================================================================
echo.
echo  Next steps:
echo   1. Review and modify env.bat for your production database
echo   2. Run start_prod.bat to start the services
echo.
pause
endlocal