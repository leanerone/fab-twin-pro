@echo off
setlocal

title FabTwin Direct Mode (No IIS)

echo ================================================================
echo  FabTwin Direct Mode Start (No IIS)
echo  Backend: 8002  |  Frontend: Vite preview 5173
echo ================================================================
echo.
echo  Architecture:
echo    - HTTP API:  browser -> Vite:5173 -> proxy -> backend:8002
echo    - WebSocket: browser -> Vite:5173 -> proxy -> backend:8002
echo    - Static:    Vite serves frontend\dist (preview mode)
echo.
echo  NOTE: This mode does NOT need IIS. Vite proxy handles both
echo        HTTP and WebSocket natively. Use this if IIS has issues.
echo.

set "BASE_DIR=%~dp0"
set "BASE_DIR=%BASE_DIR:~0,-1%"
set "BACKEND_DIR=%BASE_DIR%\backend"
set "FRONTEND_DIR=%BASE_DIR%\frontend"

REM ----- Check Python -----
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in PATH
    echo Please install Python 3.11+ first
    pause
    exit /b 1
)
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PY_VER=%%i
echo [OK] Python: %PY_VER%

REM ----- Check Node.js -----
where node >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js not found in PATH
    echo Please install Node.js 18+ first
    pause
    exit /b 1
)
for /f "tokens=1" %%i in ('node --version 2^>^&1') do set NODE_VER=%%i
echo [OK] Node.js: %NODE_VER%
echo.

REM ----- Load env.bat -----
if exist "%BASE_DIR%\env.bat" (
    echo [INFO] Loading env.bat...
    call "%BASE_DIR%\env.bat"
    echo   DB_TYPE: %DB_TYPE%
    echo   ORACLE_HOST: %ORACLE_HOST%
    echo   ORACLE_USER: %ORACLE_USER%
    echo   ORACLE_CLIENT_DIR: %ORACLE_CLIENT_DIR%
) else (
    echo [WARN] env.bat not found, using defaults
    set "DB_TYPE=sqlite"
)
echo.

REM ----- Auto-create backend venv if missing -----
cd /d "%BACKEND_DIR%"
if not exist "venv\Scripts\python.exe" (
    echo ================================================================
    echo  venv not found, creating virtual environment...
    echo ================================================================
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create venv
        pause
        exit /b 1
    )
    echo [OK] venv created

    echo Upgrading pip...
    venv\Scripts\python.exe -m pip install --upgrade pip >nul 2>&1

    echo Installing dependencies...
    if exist "wheels" (
        echo   Found wheels directory, installing OFFLINE...
        venv\Scripts\pip.exe install --no-index --find-links=wheels -r requirements.txt
    ) else (
        echo   No wheels directory, installing ONLINE...
        venv\Scripts\pip.exe install -r requirements.txt
    )
    if errorlevel 1 (
        echo [ERROR] pip install failed
        pause
        exit /b 1
    )
    echo [OK] Dependencies installed
    echo ================================================================
) else (
    echo [OK] venv already exists
)
echo.

REM ----- Verify critical packages -----
echo [INFO] Checking critical packages...
venv\Scripts\python.exe -c "import fastapi; print('  fastapi:', fastapi.__version__)" 2>nul || echo [WARN] fastapi not found!
venv\Scripts\python.exe -c "import sqlalchemy; print('  sqlalchemy:', sqlalchemy.__version__)" 2>nul || echo [WARN] sqlalchemy not found!
echo.

REM ----- Check frontend build -----
if not exist "%FRONTEND_DIR%\dist\index.html" (
    echo [INFO] Frontend dist not found, need to build...
    cd /d "%FRONTEND_DIR%"
    if not exist "node_modules" (
        echo Installing npm dependencies...
        call npm install
        if errorlevel 1 (
            echo [ERROR] npm install failed
            pause
            exit /b 1
        )
    )
    echo Building frontend...
    call npm run build
    if errorlevel 1 (
        echo [ERROR] Frontend build failed
        pause
        exit /b 1
    )
    echo [OK] Frontend built
) else (
    echo [OK] Frontend dist found
)
echo.

REM ----- Start backend -----
echo [1/2] Starting backend (FastAPI :8002)...

set "BACKEND_LAUNCHER=%BACKEND_DIR%\_run_direct.bat"
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
echo echo ====================== >> "%BACKEND_LAUNCHER%"
echo venv\Scripts\python.exe main.py >> "%BACKEND_LAUNCHER%"

start "FabTwin Backend" cmd /k "%BACKEND_LAUNCHER%"
timeout /t 3 /nobreak >nul

REM ----- Start frontend (Vite preview) -----
echo [2/2] Starting frontend (Vite preview :5173)...
cd /d "%FRONTEND_DIR%"
start "FabTwin Frontend" cmd /k "cd /d %FRONTEND_DIR% && npx vite preview --host"

echo.
echo ================================================================
echo  Direct Mode Started!
echo ================================================================
echo.
echo  Frontend:   http://SERVER-IP:5173  (Vite preview)
echo  Backend:    http://SERVER-IP:8002  (FastAPI direct)
echo  WebSocket:  ws://SERVER-IP:5173/ws/realtime  (Vite proxy -> 8002)
echo  API docs:   http://SERVER-IP:8002/docs
echo.
echo  No IIS needed. Vite proxy handles HTTP + WebSocket natively.
echo.
echo  Close both windows to stop services.
echo.
pause
endlocal
