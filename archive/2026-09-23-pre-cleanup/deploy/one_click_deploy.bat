@echo off
chcp 65001 >nul
setlocal

title FabTwin One-Click Full Deploy

echo ================================================================
echo  FabTwin One-Click Full Deployment
echo  (New Server Setup - All In One)
echo ================================================================
echo.

REM SCRIPT_DIR=deploy 目录（找 env.bat），BASE_DIR=项目根（找 backend/frontend），脚本已移至 deploy 子目录
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
pushd "%SCRIPT_DIR%\.."
set "BASE_DIR=%CD%"
popd
set "BACKEND_DIR=%BASE_DIR%\backend"
set "FRONTEND_DIR=%BASE_DIR%\frontend"

echo [1/8] Checking prerequisites...
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found! Please install Python 3.11+ and check "Add to PATH"
    pause
    exit /b 1
)
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PY_VER=%%i
echo   Python: %PY_VER%

where node >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js not found! Please install Node.js 18+
    pause
    exit /b 1
)
for /f "tokens=1" %%i in ('node --version 2^>^&1') do set NODE_VER=%%i
echo   Node.js: %NODE_VER%
echo.

echo [2/8] Loading env.bat...
set DB_TYPE=
set ORACLE_HOST=
set ORACLE_USER=
set ORACLE_SERVICE=
set ORACLE_CLIENT_DIR=

if exist "%SCRIPT_DIR%\env.bat" (
    echo   Found env.bat, loading...
    call "%SCRIPT_DIR%\env.bat"
) else (
    echo   [WARN] env.bat not found
)

REM Verify variables were loaded
echo   DB_TYPE=[%DB_TYPE%]
echo   ORACLE_HOST=[%ORACLE_HOST%]
echo   ORACLE_USER=[%ORACLE_USER%]
echo   ORACLE_SERVICE=[%ORACLE_SERVICE%]

if "%DB_TYPE%"=="" (
    echo   [ERROR] DB_TYPE is empty!
    echo   Please edit env.bat and set your Oracle database connection settings.
    echo.
    echo   Example env.bat content for Oracle:
    echo     set DB_TYPE=oracle
    echo     set ORACLE_HOST=10.30.8.119
    echo     set ORACLE_PORT=1521
    echo     set ORACLE_SERVICE=APCDB
    echo     set ORACLE_USER=emuuser
    echo     set ORACLE_PASSWORD=apcuser
    echo     set ORACLE_DSN_TYPE=sid
    echo     set ORACLE_CLIENT_DIR=C:\app\client\c11463\product\19.0.0\client_1
    echo.
    pause
    exit /b 1
)
echo.

echo [3/8] Setting up backend venv...
cd /d "%BACKEND_DIR%"
if not exist "venv\Scripts\python.exe" (
    echo   Creating venv...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create venv
        pause
        exit /b 1
    )
) else (
    echo   venv already exists
)
echo.

echo [4/8] Installing Python dependencies...
echo   This may take a few minutes...
venv\Scripts\python.exe -m pip install --upgrade pip >nul 2>&1

REM 离线安装：检测 wheels 目录，优先用离线包（内网环境必须）
if exist "wheels" (
    echo   Found wheels directory, installing OFFLINE...
    venv\Scripts\pip.exe install --no-index --find-links=wheels -r requirements.txt
) else (
    echo   No wheels directory, installing ONLINE...
    venv\Scripts\pip.exe install -r requirements.txt
)
if errorlevel 1 (
    echo [ERROR] pip install failed
    echo   If offline: ensure wheels directory exists with all packages
    echo   If online: check network connection
    pause
    exit /b 1
)
echo.

echo [5/8] Verifying backend packages...
venv\Scripts\python.exe -c "import fastapi; print('  fastapi:', fastapi.__version__)" 2>nul
venv\Scripts\python.exe -c "import sqlalchemy; print('  sqlalchemy:', sqlalchemy.__version__)" 2>nul
venv\Scripts\python.exe -c "import oracledb; print('  oracledb:', oracledb.__version__)" 2>nul
echo.

echo [6/8] Setting up frontend...
cd /d "%FRONTEND_DIR%"
if not exist "node_modules" (
    echo   Installing npm dependencies...
    call npm install
    if errorlevel 1 (
        echo [ERROR] npm install failed
        pause
        exit /b 1
    )
) else (
    echo   node_modules already exists
)
echo.

echo [7/8] Building frontend...
cd /d "%FRONTEND_DIR%"
call npm run build
if errorlevel 1 (
    echo [ERROR] Frontend build failed
    pause
    exit /b 1
)
echo   Frontend built successfully
echo.

echo [8/8] Testing database connection...
cd /d "%BASE_DIR%"
call "backend\venv\Scripts\python.exe" backend\_test_db.py
if errorlevel 1 (
    echo   [WARN] DB connection failed - check env.bat settings
) else (
    echo   Database: OK
)
echo.

echo ================================================================
echo  Deployment Complete!
echo ================================================================
echo.
echo  Next steps:
echo   1. Configure IIS: run deploy_iis_nt_final.bat
echo   2. Start backend:  run start_backend.bat
echo   3. Or start dev:   run start-dev.bat
echo.
pause
endlocal
