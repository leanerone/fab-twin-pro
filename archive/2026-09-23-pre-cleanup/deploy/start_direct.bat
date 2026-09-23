@echo off
REM FabTwin Direct Mode (No IIS) - BAT version
REM This bat just delegates to the PowerShell version for encoding safety.

chcp 65001 >nul 2>&1
setlocal

title FabTwin Direct Mode (No IIS)

echo ================================================================
echo  FabTwin Direct Mode Start (No IIS)
echo  Backend: 8002  |  Frontend: Vite preview 5173
echo ================================================================
echo.

REM Get script directory
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

REM Run PowerShell version (bypass execution policy for this process)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%\start_direct.ps1"

endlocal
