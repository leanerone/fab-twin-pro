@echo off
setlocal

title FabTwin Backend Only

set "BASE_DIR=%~dp0"
set "BACKEND_DIR=%BASE_DIR%backend"

echo ================================================================
echo  FabTwin Backend Only Start
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

if not exist "%BACKEND_DIR%\venv\Scripts\python.exe" (
    echo ERROR: backend venv not found
    echo Please run deploy.bat first
    pause
    exit /b 1
)

netstat -ano | findstr ":8002 " | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo WARNING: Port 8002 already in use
    choice /C YN /M "Continue anyway"
    if errorlevel 2 exit /b 0
)

echo [1/1] Starting backend (FastAPI :8002)...

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
