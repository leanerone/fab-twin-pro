@echo off
setlocal

echo ================================================================
echo  FabTwin Deployment Fix Tool
echo ================================================================
echo.

net session >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Please run as Administrator!
    echo [INFO] Right-click this bat file and select "Run as administrator"
    pause
    exit /b 1
)

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

:: ================================================================
:: Fix 1: Kill existing backend processes
:: ================================================================
echo --- [1/5] Killing existing backend processes ---
echo.

netstat -ano | findstr ":8002 " | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo [INFO] Killing process on port 8002...
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8002 " ^| findstr "LISTENING"') do (
        taskkill /F /PID %%a >nul 2>&1
        echo [OK] Killed PID: %%a
    )
) else (
    echo [INFO] No process on port 8002
)

echo.

:: ================================================================
:: Fix 2: Copy frontend files to IIS
:: ================================================================
echo --- [2/5] Copying frontend files to IIS ---
echo.

set "IIS_SITE_DIR=C:\inetpub\wwwroot\FabTwin"
set "DIST_DIR=frontend\dist"

if exist "%DIST_DIR%" (
    echo [INFO] Source: %DIST_DIR%
    echo [INFO] Target: %IIS_SITE_DIR%
    echo.
    
    if not exist "%IIS_SITE_DIR%" mkdir "%IIS_SITE_DIR%"
    
    del /s /q "%IIS_SITE_DIR%\*" >nul 2>&1
    xcopy /E /I /Y "%DIST_DIR%\*" "%IIS_SITE_DIR%\"
    
    if errorlevel 1 (
        echo [ERROR] Copy failed!
    ) else (
        echo [OK] Frontend files copied successfully
    )
) else (
    echo [ERROR] %DIST_DIR% NOT found!
    echo [INFO] Please run: cd frontend && npm run build
)

echo.

:: ================================================================
:: Fix 3: Update web.config
:: ================================================================
echo --- [3/5] Updating web.config ---
echo.

(
echo ^<?xml version="1.0" encoding="UTF-8"?^>
echo ^<configuration^>
echo   ^<system.webServer^>
echo     ^<security^>
echo       ^<authentication^>
echo         ^<anonymousAuthentication enabled="true" /^>
echo         ^<windowsAuthentication enabled="false" /^>
echo       ^</authentication^>
echo     ^</security^>
echo     ^<rewrite^>
echo       ^<rules^>
echo         ^<rule name="APIProxy" stopProcessing="true"^>
echo           ^<match url="^api/(.*)" /^>
echo           ^<action type="Rewrite" url="http://127.0.0.1:8002/api/{R:1}" /^>
echo         ^</rule^>
echo         ^<rule name="WSProxy" stopProcessing="true"^>
echo           ^<match url="^ws/(.*)" /^>
echo           ^<action type="Rewrite" url="http://127.0.0.1:8002/ws/{R:1}" /^>
echo         ^</rule^>
echo         ^<rule name="SpaFallback" stopProcessing="true"^>
echo           ^<match url="^(.*)$" /^>
echo           ^<conditions^>
echo             ^<add input="{REQUEST_FILENAME}" matchType="IsFile" negate="true" /^>
echo             ^<add input="{REQUEST_FILENAME}" matchType="IsDirectory" negate="true" /^>
echo           ^</conditions^>
echo           ^<action type="Rewrite" url="index.html" /^>
echo         ^</rule^>
echo       ^</rules^>
echo     ^</rewrite^>
echo     ^<httpProtocol^>
echo       ^<customHeaders^>
echo         ^<add name="X-Forwarded-For" value="{REMOTE_ADDR}" /^>
echo         ^<add name="X-Forwarded-User" value="{REMOTE_USER}" /^>
echo       ^</customHeaders^>
echo     ^</httpProtocol^>
echo     ^<staticContent^>
echo       ^<mimeMap fileExtension=".*" mimeType="application/octet-stream" /^>
echo     ^</staticContent^>
echo     ^<httpErrors errorMode="Detailed" /^>
echo   ^</system.webServer^>
echo ^</configuration^>
) > "%IIS_SITE_DIR%\web.config"

echo [OK] web.config updated.

echo.

:: ================================================================
:: Fix 4: Reset IIS
:: ================================================================
echo --- [4/5] Resetting IIS ---
echo.

echo [INFO] Stopping IIS...
iisreset /stop >nul 2>&1
echo [OK] IIS stopped.

timeout /t 2 /nobreak >nul

echo [INFO] Starting IIS...
iisreset /start >nul 2>&1
echo [OK] IIS started.

echo [INFO] Starting FabTwin site...
%WINDIR%\System32\inetsrv\appcmd.exe start site /site.name:FabTwin >nul 2>&1
echo [OK] FabTwin site started.

echo.

:: ================================================================
:: Fix 5: Restart backend
:: ================================================================
echo --- [5/5] Starting backend ---
echo.

echo [INFO] Starting backend service...
call "%SCRIPT_DIR%start_backend.bat"

echo.
echo ================================================================
echo  Fix Complete!
echo ================================================================
echo.
echo [NEXT STEPS]
echo 1. Wait for backend to start (check the new window)
echo 2. Open browser and visit http://服务器IP or http://localhost
echo 3. Login with admin/admin123 (if using password login)
echo.
echo [TROUBLESHOOTING]
echo - If still IIS welcome page: check port 80 conflicts
echo - If API error: check backend is running on port 8002
echo - Run .\check_deployment.bat for detailed diagnostic
echo.
pause

endlocal