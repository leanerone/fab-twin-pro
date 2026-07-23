@echo off
setlocal

title FabTwin IIS Mode (Backend + IIS)

echo ================================================================
echo  FabTwin IIS Mode Start
echo  Backend: 8002  |  IIS: 80  |  WebSocket: direct to 8002
echo ================================================================
echo.
echo  Architecture:
echo    - HTTP API:  browser -> IIS:80 -> URL Rewrite -> backend:8002
echo    - WebSocket: browser -> backend:8002 (direct, bypass IIS)
echo    - Static:    IIS serves frontend\dist
echo.
echo  NOTE: WebSocket bypasses IIS because URL Rewrite cannot
echo        proxy WebSocket upgrade handshake. Frontend auto-detects
echo        IIS (port 80) and connects WS directly to port 8002.
echo.

set "BASE_DIR=%~dp0"
set "BASE_DIR=%BASE_DIR:~0,-1%"
set "BACKEND_DIR=%BASE_DIR%\backend"

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

REM ----- Auto-create venv if missing -----
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
venv\Scripts\python.exe -c "import oracledb; print('  oracledb:', oracledb.__version__)" 2>nul || echo [WARN] oracledb not found!
echo.

REM ----- Check IIS frontend files -----
set "IIS_SITE_DIR=C:\inetpub\wwwroot\FabTwin"
if not exist "%IIS_SITE_DIR%\index.html" (
    echo [WARN] IIS frontend not found at %IIS_SITE_DIR%
    echo [INFO] Please run deploy_iis_nt_final.bat first to deploy frontend to IIS
    echo.
) else (
    echo [OK] IIS frontend found at %IIS_SITE_DIR%
)
echo.

REM ----- Check port 8002 -----
netstat -ano | findstr ":8002 " | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo [WARN] Port 8002 already in use
    choice /C YN /M "Continue anyway"
    if errorlevel 2 exit /b 0
)

REM ----- Start backend -----
echo [1/1] Starting backend (FastAPI :8002)...

set "BACKEND_LAUNCHER=%BACKEND_DIR%\_run_iis.bat"
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
echo  IIS Mode Started!
echo ================================================================
echo.
echo  Frontend:   http://SERVER-IP         (IIS port 80)
echo  Backend:    http://SERVER-IP:8002     (FastAPI direct)
echo  WebSocket:  ws://SERVER-IP:8002/ws/realtime  (direct, bypass IIS)
echo  API docs:   http://SERVER-IP:8002/docs
echo.
echo  IMPORTANT: Open port 8002 in Windows Firewall for WebSocket!
echo    netsh advfirewall firewall add rule name="FabTwin Backend" ^
echo      dir=in action=allow protocol=TCP localport=8002
echo.
echo  Close the backend window to stop.
echo.
pause
endlocal
