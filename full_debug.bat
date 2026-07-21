@echo off
setlocal

echo ================================================================
echo FabTwin Full Debug - End-to-end chain check
echo ================================================================
echo.

REM Load env.bat if exists
if exist "%~dp0env.bat" call "%~dp0env.bat"

cd /d "%~dp0"
backend\venv\Scripts\python.exe _full_debug.py

echo.
echo ================================================================
pause
