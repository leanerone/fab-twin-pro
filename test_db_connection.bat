@echo off
setlocal

title FabTwin Oracle DB Connection Test

set "BASE_DIR=%~dp0"
set "BASE_DIR=%BASE_DIR:~0,-1%"
set "BACKEND_DIR=%BASE_DIR%\backend"
set "PY_EXE=%BACKEND_DIR%\venv\Scripts\python.exe"

echo ===============================================================
echo  FabTwin Oracle DB Connection Test
echo ===============================================================
echo.

if not exist "%PY_EXE%" (
    echo ERROR: Python not found at %PY_EXE%
    echo Please run deploy.bat first to create venv.
    pause
    exit /b 1
)

"%PY_EXE%" "%BASE_DIR%\_test_db.py"

echo.
echo ===============================================================
echo  Done. Report: %BASE_DIR%\db_connection_report.txt
echo ===============================================================
pause
endlocal
