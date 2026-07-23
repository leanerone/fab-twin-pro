@echo off
REM FabTwin Backend Only - BAT version
REM This bat just delegates to the PowerShell version.

chcp 65001 >nul 2>&1
setlocal

title FabTwin Backend Only

echo ================================================================
echo  FabTwin Backend Only Start
echo  Backend: 8002
echo ================================================================
echo.

set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%\start_backend.ps1"

endlocal
