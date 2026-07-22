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

:: Fix 1: Kill backend
echo --- [1/4] Stopping existing backend ---
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

:: Fix 2: Copy frontend files
echo --- [2/4] Copying frontend files to IIS ---
echo.

set "IIS_SITE_DIR=C:\inetpub\wwwroot\FabTwin"
set "DIST_DIR=frontend\dist"

if not exist "%DIST_DIR%" (
    echo [ERROR] %DIST_DIR% NOT found!
    echo [INFO] Please run: cd frontend ^& npm run build
    pause
    exit /b 1
)

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

echo.

:: Fix 3: Update web.config
echo --- [3/4] Updating web.config ---
echo.

(
echo ^<?xml version="1.0" encoding="UTF-8"?^>
echo ^<configuration^>
echo   ^<system.webServer^>
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
echo       ^</customHeaders^>
echo     ^</httpProtocol^>
echo   ^</system.webServer^>
echo ^</configuration^>
) > "%IIS_SITE_DIR%\web.config"

echo [OK] web.config updated.

echo.

:: Fix 4: Reset IIS and fix auth
echo --- [4/4] Resetting IIS ---
echo.

echo [INFO] Enabling Anonymous Authentication...
%WINDIR%\System32\inetsrv\appcmd.exe set config "FabTwin" -section:system.webServer/security/authentication/windowsAuthentication /enabled:"False" /commit:apphost >nul 2>&1
%WINDIR%\System32\inetsrv\appcmd.exe set config "FabTwin" -section:system.webServer/security/authentication/anonymousAuthentication /enabled:"True" /commit:apphost >nul 2>&1

echo [INFO] Enabling ARR Proxy...
%WINDIR%\System32\inetsrv\appcmd.exe set config -section:system.webServer/proxy /enabled:"True" /commit:apphost >nul 2>&1

echo [INFO] Restarting IIS...
iisreset /start >nul 2>&1
%WINDIR%\System32\inetsrv\appcmd.exe start site /site.name:FabTwin >nul 2>&1
echo [OK] IIS restarted.

echo.
echo ================================================================
echo  Fix Complete!
echo ================================================================
echo.
echo [NEXT STEPS]
echo 1. Start backend: .\start_backend.bat
echo 2. Open browser: http://SERVER-IP
echo 3. Login: admin / admin123
echo.
pause

endlocal
