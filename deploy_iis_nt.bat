@echo off
setlocal
title FabTwin IIS Windows Auth Deployment
echo ================================================================
echo  FabTwin IIS Windows Auth Deployment
echo ================================================================
echo.
echo  This script configures IIS with Windows Authentication
echo  for intranet NT auto-login.
echo.
echo  REQUIREMENTS:
echo    - Run as Administrator
echo    - Windows Authentication feature installed
echo    - URL Rewrite and ARR modules installed
echo.
pause
echo.

REM [1/8] Check admin
net session >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Please run as Administrator!
    pause
    exit /b 1
)
echo [OK] Running as Administrator

REM [2/8] Check IIS
echo.
echo [2/8] Checking IIS installation...
if not exist "%windir%\system32\inetsrv\appcmd.exe" (
    echo [ERROR] IIS not installed!
    pause
    exit /b 1
)
echo [OK] IIS is installed

REM [3/8] Check modules
echo.
echo [3/8] Checking required modules...
reg query "HKLM\SOFTWARE\Microsoft\IIS Extensions\URL Rewrite" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] URL Rewrite module not installed!
    pause
    exit /b 1
)
echo [OK] URL Rewrite module installed

REM [4/8] Check Windows Auth feature
echo.
echo [4/8] Checking Windows Authentication feature...
reg query "HKLM\SOFTWARE\Microsoft\InetStp\Components" /v "WindowsAuthentication" >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Windows Authentication feature may not be installed.
    echo [INFO] Please install it via: Server Manager -> Add Roles -> Web Server -> Security -> Windows Authentication
    pause
)
echo [OK] Windows Authentication feature check done

REM [5/8] Copy frontend files
echo.
echo [5/8] Copying frontend files...
set "DIST_DIR=frontend\dist"
set "IIS_SITE_DIR=C:\inetpub\wwwroot\FabTwin"
if not exist "%DIST_DIR%\index.html" (
    echo [ERROR] frontend\dist not found! Please run 'npm run build' first.
    pause
    exit /b 1
)
if not exist "%IIS_SITE_DIR%" mkdir "%IIS_SITE_DIR%"
del /s /q "%IIS_SITE_DIR%\*" >nul 2>&1
xcopy /E /I /Y "%DIST_DIR%\*" "%IIS_SITE_DIR%\"
if errorlevel 1 (
    echo [ERROR] Copy failed!
    pause
    exit /b 1
)
echo [OK] Frontend files copied

REM [6/8] Create web.config (no auth section - configured via appcmd)
echo.
echo [6/8] Creating web.config...
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
echo         ^<add name="X-Forwarded-User" value="{REMOTE_USER}" /^>
echo       ^</customHeaders^>
echo     ^</httpProtocol^>
echo   ^</system.webServer^>
echo ^</configuration^>
) > "%IIS_SITE_DIR%\web.config"
echo [OK] web.config created

REM [7/8] Configure IIS site
echo.
echo [7/8] Configuring IIS site and authentication...

REM Create AppPool
%windir%\system32\inetsrv\appcmd.exe add apppool /name:"FabTwinAppPool" /managedRuntimeVersion:"" >nul 2>&1
%windir%\system32\inetsrv\appcmd.exe set apppool "FabTwinAppPool" /processModel.identityType:"ApplicationPoolIdentity" >nul 2>&1
echo [OK] Application Pool configured

REM Create or update site
%windir%\system32\inetsrv\appcmd.exe add site /name:"FabTwin" /physicalPath:"%IIS_SITE_DIR%" /bindings:"http/*:80:" >nul 2>&1
if errorlevel 1 (
    %windir%\system32\inetsrv\appcmd.exe set site "FabTwin" /bindings:"http/*:80:" >nul 2>&1
    %windir%\system32\inetsrv\appcmd.exe set app "FabTwin/" /applicationPool:"FabTwinAppPool" >nul 2>&1
)
echo [OK] Site configured

REM Stop Default Web Site to free port 80
%windir%\system32\inetsrv\appcmd.exe stop site "Default Web Site" >nul 2>&1
echo [OK] Default Web Site stopped

REM Unlock authentication sections (required for site-level config)
echo [INFO] Unlocking authentication configuration...
%windir%\system32\inetsrv\appcmd.exe unlock config -section:system.webServer/security/authentication/anonymousAuthentication >nul 2>&1
%windir%\system32\inetsrv\appcmd.exe unlock config -section:system.webServer/security/authentication/windowsAuthentication >nul 2>&1
echo [OK] Authentication sections unlocked

REM Configure Windows Authentication (disable anonymous, enable Windows)
echo [INFO] Setting Windows Authentication...
%windir%\system32\inetsrv\appcmd.exe set config "FabTwin" -section:system.webServer/security/authentication/anonymousAuthentication /enabled:"false" >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Failed to disable Anonymous Auth. May need manual configuration in IIS Manager.
) else (
    echo [OK] Anonymous Authentication disabled
)

%windir%\system32\inetsrv\appcmd.exe set config "FabTwin" -section:system.webServer/security/authentication/windowsAuthentication /enabled:"true" >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Failed to enable Windows Auth. May need manual configuration in IIS Manager.
) else (
    echo [OK] Windows Authentication enabled
)

REM Enable ARR Proxy
%windir%\system32\inetsrv\appcmd.exe set config -section:system.webServer/proxy /enabled:"true" >nul 2>&1
echo [OK] ARR Proxy enabled

REM Start site
%windir%\system32\inetsrv\appcmd.exe start site "FabTwin" >nul 2>&1
echo [OK] FabTwin site started

REM [8/8] Verify
echo.
echo [8/8] Verifying configuration...
%windir%\system32\inetsrv\appcmd.exe list config "FabTwin" -section:system.webServer/security/authentication | findstr "enabled"

echo.
echo ================================================================
echo  Deployment Complete!
echo ================================================================
echo.
echo  Auth Mode: Windows Authentication (NT auto-login)
echo  URL:       http://SERVER-IP (port 80)
echo.
echo  IMPORTANT:
echo    - Backend must be running: .\start_backend.bat
echo    - Users will be auto-logged in with their Windows domain account
echo    - If Windows Auth fails, users can click "Account Password Login"
echo.
echo  TROUBLESHOOTING:
echo    - If 401 error: Check Windows Auth feature is installed
echo    - If 500.19: Run appcmd unlock commands manually
echo    - Access from other PCs may require domain trust
echo.
pause
endlocal
