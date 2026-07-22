@echo off
setlocal

title FabTwin Full Stack

set "BASE_DIR=%~dp0"
set "BACKEND_DIR=%BASE_DIR%backend"
set "PYTHON=%BACKEND_DIR%\venv\Scripts\python.exe"

echo ================================================================
echo  FabTwin Full Stack Startup
echo ================================================================
echo.

if exist "%BASE_DIR%env.bat" (
    call "%BASE_DIR%env.bat"
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

if not exist "%PYTHON%" (
    echo ERROR: Python venv not found
    echo Please run deploy.bat first
    pause
    exit /b 1
)

if not exist "%BASE_DIR%frontend\dist\index.html" (
    echo ERROR: frontend\dist not found
    echo Please run: cd frontend ^& npm run build
    pause
    exit /b 1
)

netstat -ano | findstr ":8002 " | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo WARNING: Port 8002 already in use, killing...
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8002 " ^| findstr "LISTENING"') do (
        taskkill /F /PID %%a >nul 2>&1
    )
)

netstat -ano | findstr ":8080 " | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo WARNING: Port 8080 already in use, killing...
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8080 " ^| findstr "LISTENING"') do (
        taskkill /F /PID %%a >nul 2>&1
    )
)

echo [1/2] Starting backend (FastAPI :8002)...

set "BACKEND_LAUNCHER=%BACKEND_DIR%\_run_backend.bat"

echo @echo off > "%BACKEND_LAUNCHER%"
echo cd /d "%BACKEND_DIR%" >> "%BACKEND_LAUNCHER%"
echo set DB_TYPE=%DB_TYPE% >> "%BACKEND_LAUNCHER%"
echo set ORACLE_HOST=%ORACLE_HOST% >> "%BACKEND_LAUNCHER%"
echo set ORACLE_PORT=%ORACLE_PORT% >> "%BACKEND_LAUNCHER%"
echo set ORACLE_SERVICE=%ORACLE_SERVICE% >> "%BACKEND_LAUNCHER%"
echo set ORACLE_USER=%ORACLE_USER% >> "%BACKEND_LAUNCHER%"
echo set ORACLE_PASSWORD=%ORACLE_PASSWORD% >> "%BACKEND_LAUNCHER%"
echo set ORACLE_DSN_TYPE=%ORACLE_DSN_TYPE% >> "%BACKEND_LAUNCHER%"
echo set ORACLE_CLIENT_DIR=%ORACLE_CLIENT_DIR% >> "%BACKEND_LAUNCHER%"
echo set SIMULATION_ENABLED=%SIMULATION_ENABLED% >> "%BACKEND_LAUNCHER%"
echo set DB_POLLER_ENABLED=%DB_POLLER_ENABLED% >> "%BACKEND_LAUNCHER%"
echo set NO_PROXY=* >> "%BACKEND_LAUNCHER%"
echo set no_proxy=* >> "%BACKEND_LAUNCHER%"
echo set HTTP_PROXY= >> "%BACKEND_LAUNCHER%"
echo set HTTPS_PROXY= >> "%BACKEND_LAUNCHER%"
echo echo === Backend Config === >> "%BACKEND_LAUNCHER%"
echo echo DB_TYPE=%DB_TYPE% >> "%BACKEND_LAUNCHER%"
echo echo ORACLE_HOST=%ORACLE_HOST% >> "%BACKEND_LAUNCHER%"
echo echo ORACLE_USER=%ORACLE_USER% >> "%BACKEND_LAUNCHER%"
echo echo ORACLE_CLIENT_DIR=%ORACLE_CLIENT_DIR% >> "%BACKEND_LAUNCHER%"
echo echo ====================== >> "%BACKEND_LAUNCHER%"
echo venv\Scripts\python.exe main.py >> "%BACKEND_LAUNCHER%"

start "FabTwin Backend" cmd /k "%BACKEND_LAUNCHER%"

echo   Backend starting... (check new window for logs)
timeout /t 5 /nobreak >nul

echo.
echo [2/2] Starting proxy server (:8080)...
start "FabTwin Proxy" cmd /k "%PYTHON%" "%BASE_DIR%start_proxy.py"

echo   Proxy server starting... (check new window for logs)
timeout /t 2 /nobreak >nul

echo.
echo ================================================================
echo  FabTwin Started Successfully!
echo ================================================================
echo.
echo  Backend:   http://localhost:8002
echo  API docs:  http://localhost:8002/docs
echo  Health:    http://localhost:8002/health
echo.
echo  Frontend:  http://SERVER-IP:8080
echo             http://localhost:8080
echo.
echo  Login:     admin / admin123
echo.
echo  [IMPORTANT]
echo  - Keep both command windows open while using FabTwin
echo  - Close both windows to stop the service
echo  - If port 8080 is occupied, set PROXY_PORT=8081 before running
echo.
pause
endlocal
