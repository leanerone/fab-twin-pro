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

REM Check backend running on 8002
curl -s http://127.0.0.1:8002/api/health >nul 2>&1
if errorlevel 1 (
    echo [WARN] Backend not running on port 8002.
    echo [WARN] Please run start_prod.bat first.
    echo.
)

echo ================================================================
echo  FabTwin One-Click Proxy Server
echo ================================================================
echo.
echo [INFO] Starting proxy server...
echo [INFO] Access: http://%%COMPUTERNAME%%:8080 or http://this-server-ip:8080
echo [INFO] Backend target: http://127.0.0.1:8002
echo [INFO] If you need port 80, please run as Administrator or set PROXY_PORT=80
echo.

"%PYTHON%" start_proxy.py

if errorlevel 1 (
    echo [ERROR] Proxy failed.
    pause
)

endlocal
