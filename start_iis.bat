@echo off
REM FabTwin IIS Mode (Backend Only) - BAT version
REM This bat just delegates to the PowerShell version.

chcp 65001 >nul 2>&1
setlocal

title FabTwin IIS Mode (Backend + IIS)

echo ================================================================
echo  FabTwin IIS Mode Start
echo  Backend: 8002  |  IIS: 80
echo ================================================================
echo.

set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%\start_iis.ps1"

endlocal
