@echo off
setlocal

echo ================================================================
echo Direct Oracle Check (hardcoded config)
echo ================================================================
echo.

cd /d "%~dp0"
backend\venv\Scripts\python.exe _direct_oracle_check.py

echo.
echo ================================================================
pause
