@echo off
setlocal

echo ================================================================
echo Fix model_id mismatch (VPO-2200 -> PODOPENER-2200)
echo ================================================================
echo.

if exist "%~dp0env.bat" call "%~dp0env.bat"

cd /d "%~dp0"
backend\venv\Scripts\python.exe _fix_model_id.py

echo.
echo ================================================================
pause
