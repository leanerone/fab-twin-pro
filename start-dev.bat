@echo off
setlocal

title FabTwin Dev Start

set "BASE_DIR=%~dp0"
set "BASE_DIR=%BASE_DIR:~0,-1%"
set "BACKEND_DIR=%BASE_DIR%\backend"
set "FRONTEND_DIR=%BASE_DIR%\frontend"

echo ================================================================
echo  FabTwin Development Start
echo ================================================================
echo.

REM ----- Load env.bat (Oracle only, no SQLite fallback) -----
if exist "%BASE_DIR%\env.bat" (
    echo [INFO] Loading env.bat...
    call "%BASE_DIR%\env.bat"
    echo   DB_TYPE: %DB_TYPE%
    echo   ORACLE_HOST: %ORACLE_HOST%
    echo   ORACLE_USER: %ORACLE_USER%
    echo   ORACLE_SERVICE: %ORACLE_SERVICE%
    echo   ORACLE_CLIENT_DIR: %ORACLE_CLIENT_DIR%
) else (
    echo [ERROR] env.bat not found! Oracle connection required.
    pause
    exit /b 1
)
echo.

REM ----- Auto-create backend venv if missing -----
cd /d "%BACKEND_DIR%"
if not exist "venv\Scripts\python.exe" (
    echo [INFO] Backend venv not found, auto-creating...
    python -m venv venv
    if errorlevel 1 (
        echo ERROR: Failed to create venv
        pause
        exit /b 1
    )
    echo [INFO] Installing dependencies...
    venv\Scripts\python.exe -m pip install --upgrade pip >nul 2>&1
    if exist "wheels" (
        echo   Found wheels directory, installing OFFLINE...
        venv\Scripts\pip.exe install --no-index --find-links=wheels -r requirements.txt
    ) else (
        echo   No wheels directory, installing ONLINE...
        venv\Scripts\pip.exe install -r requirements.txt
    )
    if errorlevel 1 (
        echo ERROR: pip install failed
        pause
        exit /b 1
    )
    echo [OK] Dependencies installed.
)

REM ----- Start backend with env vars -----
echo [1/2] Starting backend (FastAPI :8002)...
set "BACKEND_LAUNCHER=%BACKEND_DIR%\_run_backend_dev.bat"
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
echo venv\Scripts\python.exe main.py >> "%BACKEND_LAUNCHER%"
start "FabTwin Backend" cmd /k "%BACKEND_LAUNCHER%"

timeout /t 3 /nobreak >nul

REM ----- Start frontend -----
echo [2/2] Starting frontend (Vite :5173)...
cd /d "%FRONTEND_DIR%"
if not exist "node_modules" (
    echo [INFO] Installing npm dependencies...
    call npm install
    if errorlevel 1 (
        echo ERROR: npm install failed
        pause
        exit /b 1
    )
)
start "FabTwin Frontend" cmd /k "cd /d %FRONTEND_DIR% && npm run dev"

echo.
echo ================================================================
echo  Started!
echo  Frontend: http://localhost:5173
echo  Backend:  http://localhost:8002
echo  API docs: http://localhost:8002/docs
echo ================================================================
echo.
echo  Close the windows to stop services.
echo.
pause
endlocal
