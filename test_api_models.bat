@echo off
setlocal
call "%~dp0env.bat" 2>nul

echo ============================================================
echo Test API Models
echo ============================================================
echo.

cd /d "%~dp0"
backend\venv\Scripts\python.exe _test_api_models.py

echo.
echo ============================================================
pause
