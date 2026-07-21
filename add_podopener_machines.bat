@echo off
setlocal

echo ================================================================
echo Add PODOPENER-2 ~ PODOPENER-7 machines
echo ================================================================
echo.

if exist "%~dp0env.bat" call "%~dp0env.bat"

cd /d "%~dp0"
backend\venv\Scripts\python.exe add_podopener_machines.py

echo.
echo ================================================================
pause
endlocal