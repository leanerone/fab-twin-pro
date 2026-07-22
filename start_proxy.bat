@echo off
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

set "PYTHON=backend\venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo [ERROR] Python not found: %PYTHON%
    echo [ERROR] Please run deploy.bat first.
    pause
    exit /b 1
)

if not exist "frontend\dist\index.html" (
    echo [WARN] frontend\dist not found.
    echo [WARN] Please run 'npm run build' in frontend folder first.
    pause
    exit /b 1
)

echo ================================================================
echo  FabTwin One-Click Proxy Server
echo ================================================================
echo.
echo [INFO] Starting proxy server...
echo [INFO] Access: http://%%COMPUTERNAME%% or http://this-server-ip
echo.

"%PYTHON%" start_proxy.py

if errorlevel 1 (
    echo [ERROR] Proxy failed.
    pause
)

endlocal
