@echo off
setlocal

title FabTwin Backend Only

echo ================================================================
echo  FabTwin Backend Only Start
echo ================================================================
echo.

set "BASE_DIR=%~dp0"
set "BASE_DIR=%BASE_DIR:~0,-1%"
set "BACKEND_DIR=%BASE_DIR%\backend"

echo [DEBUG] BASE_DIR=%BASE_DIR%
echo [DEBUG] BACKEND_DIR=%BACKEND_DIR%
echo.

REM ----- Check Python first -----
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in PATH
    echo Please install Python 3.11+ first
    echo.
    echo Download: https://www.python.org/downloads/
    echo During install, check "Add Python to PATH"
    echo.
    pause
    exit /b 1
)
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PY_VER=%%i
echo [OK] Python found: %PY_VER%

REM ----- Check Node.js (needed for frontend build) -----
where node >nul 2>&1
if errorlevel 1 (
    echo [WARN] Node.js not found (only needed for frontend build)
) else (
    for /f "tokens=1" %%i in ('node --version 2^>^&1') do set NODE_VER=%%i
    echo [OK] Node.js found: %NODE_VER%
)
echo.

REM ----- Load env.bat -----
if exist "%BASE_DIR%\env.bat" (
    echo [INFO] Loading env.bat...
    call "%BASE_DIR%\env.bat"
    echo   DB_TYPE: %DB_TYPE%
    echo   ORACLE_HOST: %ORACLE_HOST%
    echo   ORACLE_USER: %ORACLE_USER%
    echo   ORACLE_SERVICE: %ORACLE_SERVICE%
    echo   ORACLE_CLIENT_DIR: %ORACLE_CLIENT_DIR%
) else (
    echo [WARN] env.bat not found, using defaults
    set "DB_TYPE=sqlite"
)
echo.

REM ----- Auto-create venv if missing -----
cd /d "%BACKEND_DIR%"
echo [DEBUG] Current dir: %cd%

if not exist "venv\Scripts\python.exe" (
    echo ================================================================
    echo  venv not found, creating virtual environment...
    echo ================================================================
    echo.
    
    echo [STEP 1/3] Creating Python virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create venv!
        echo Please check Python installation
        pause
        exit /b 1
    )
    echo [OK] venv created successfully
    echo.
    
    echo [STEP 2/3] Upgrading pip...
    venv\Scripts\python.exe -m pip install --upgrade pip
    if errorlevel 1 (
        echo [WARN] pip upgrade failed, continuing...
    )
    echo.
    
    echo [STEP 3/3] Installing dependencies from requirements.txt...
    if not exist "requirements.txt" (
        echo [ERROR] requirements.txt not found in %BACKEND_DIR%
        echo Please copy requirements.txt from the project
        pause
        exit /b 1
    )
    echo   This may take a few minutes...
    venv\Scripts\pip.exe install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] pip install failed!
        echo Try running manually:
        echo   cd %BACKEND_DIR%
        echo   venv\Scripts\pip.exe install -r requirements.txt
        pause
        exit /b 1
    )
    echo.
    echo [OK] All dependencies installed!
    echo ================================================================
    echo.
) else (
    echo [OK] venv already exists, skipping installation
)

REM ----- Verify venv works -----
echo [INFO] Verifying venv...
venv\Scripts\python.exe --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] venv python is broken! Try deleting venv folder and re-run
    pause
    exit /b 1
)

REM ----- Check for critical packages -----
echo [INFO] Checking critical packages...
venv\Scripts\python.exe -c "import fastapi; print('  fastapi:', fastapi.__version__)" 2>nul || echo [WARN] fastapi not found!
venv\Scripts\python.exe -c "import sqlalchemy; print('  sqlalchemy:', sqlalchemy.__version__)" 2>nul || echo [WARN] sqlalchemy not found!
venv\Scripts\python.exe -c "import oracledb; print('  oracledb:', oracledb.__version__)" 2>nul || echo [WARN] oracledb not found!
echo.

REM ----- Check port -----
netstat -ano | findstr ":8002 " | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo [WARN] Port 8002 already in use
    choice /C YN /M "Continue anyway"
    if errorlevel 2 exit /b 0
)

echo [1/1] Starting backend (FastAPI :8002)...

REM Write launcher script with env vars
set "BACKEND_LAUNCHER=%BACKEND_DIR%\_run_backend.bat"

echo @echo off > "%BACKEND_LAUNCHER%"
echo cd /d "%BACKEND_DIR%" >> "%BACKEND_LAUNCHER%"
echo set "DB_TYPE=%DB_TYPE%" >> "%BACKEND_LAUNCHER%"
echo set "ORACLE_HOST=%ORACLE_HOST%" >> "%BACKEND_LAUNCHER%"
echo set "ORACLE_PORT=%ORACLE_PORT%" >> "%BACKEND_LAUNCHER%"
echo set "ORACLE_SERVICE=%ORACLE_SERVICE%" >> "%BACKEND_LAUNCHER%"
echo set "ORACLE_USER=%ORACLE_USER%" >> "%BACKEND_LAUNCHER%"
echo set "ORACLE_PASSWORD=%ORACLE_PASSWORD%" >> "%BACKEND_LAUNCHER%"
echo set "ORACLE_DSN_TYPE=%ORACLE_DSN_TYPE%" >> "%BACKEND_LAUNCHER%"
echo set "ORACLE_CLIENT_DIR=%ORACLE_CLIENT_DIR%" >> "%BACKEND_LAUNCHER%"
echo set "SIMULATION_ENABLED=%SIMULATION_ENABLED%" >> "%BACKEND_LAUNCHER%"
echo set "DB_POLLER_ENABLED=%DB_POLLER_ENABLED%" >> "%BACKEND_LAUNCHER%"
echo set "NO_PROXY=*" >> "%BACKEND_LAUNCHER%"
echo set "no_proxy=*" >> "%BACKEND_LAUNCHER%"
echo set "HTTP_PROXY=" >> "%BACKEND_LAUNCHER%"
echo set "HTTPS_PROXY=" >> "%BACKEND_LAUNCHER%"
echo echo === Backend Config === >> "%BACKEND_LAUNCHER%"
echo echo DB_TYPE=%DB_TYPE% >> "%BACKEND_LAUNCHER%"
echo echo ORACLE_HOST=%ORACLE_HOST% >> "%BACKEND_LAUNCHER%"
echo echo ORACLE_USER=%ORACLE_USER% >> "%BACKEND_LAUNCHER%"
echo echo ORACLE_CLIENT_DIR=%ORACLE_CLIENT_DIR% >> "%BACKEND_LAUNCHER%"
echo echo ====================== >> "%BACKEND_LAUNCHER%"
echo venv\Scripts\python.exe main.py >> "%BACKEND_LAUNCHER%"

start "FabTwin Backend" cmd /k "%BACKEND_LAUNCHER%"

echo   Backend starting... (check new window for logs)
timeout /t 3 /nobreak >nul

echo.
echo ================================================================
echo  Backend Started!
echo ================================================================
echo.
echo  Backend:   http://localhost:8002
echo  API docs:  http://localhost:8002/docs
echo  Health:    http://localhost:8002/health
echo.
echo  IIS Frontend: http://SERVER-IP (port 80)
echo.
echo  Close the backend window to stop.
echo.
pause
endlocal
