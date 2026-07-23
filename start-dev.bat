@echo off
setlocal

title FabTwin Dev Start

set "BASE_DIR=%~dp0"
set "BACKEND_DIR=%BASE_DIR%\backend"
set "FRONTEND_DIR=%BASE_DIR%\frontend"

echo ================================================================
echo  FabTwin Development Start
echo ================================================================
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
    venv\Scripts\pip.exe install -r requirements.txt
    if errorlevel 1 (
        echo ERROR: pip install failed
        pause
        exit /b 1
    )
    echo [OK] Dependencies installed.
)

REM ----- Start backend -----
echo [1/2] Starting backend (FastAPI :8002)...
start "FabTwin Backend" cmd /k "cd /d %BACKEND_DIR% && venv\Scripts\python.exe main.py"

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
