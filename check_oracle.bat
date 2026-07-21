@echo off
setlocal

title FabTwin Oracle Diagnostic Tool

set "BASE_DIR=%~dp0"
set "BASE_DIR=%BASE_DIR:~0,-1%"
set "BACKEND_DIR=%BASE_DIR%\backend"
set "PY_EXE=%BACKEND_DIR%\venv\Scripts\python.exe"

echo ===============================================================
echo  FabTwin Oracle Client Diagnostic Tool
echo ===============================================================
echo.

if not exist "%PY_EXE%" (
    echo ERROR: Python not found at %PY_EXE%
    echo Please run deploy.bat first to create venv.
    pause
    exit /b 1
)

REM Run all diagnostic logic in Python (avoids all cmd parsing issues)
"%PY_EXE%" -c "import sys; sys.path.insert(0, r'%BACKEND_DIR%'); exec(open(r'%BASE_DIR%\_check_oracle.py', encoding='utf-8').read())"

echo.
echo ===============================================================
echo  Done. Report saved to: %BASE_DIR%\oracle_check_report.txt
echo ===============================================================
pause
endlocal
