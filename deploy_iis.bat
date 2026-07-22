@echo off
setlocal enabledelayedexpansion

:: ================================================================
:: FabTwin IIS Reverse Proxy Deployment
:: One-click deploy IIS + Windows Auth + Reverse Proxy
:: Run this as Administrator
:: ================================================================

echo ================================================================
echo  FabTwin IIS Reverse Proxy Deployment
echo ================================================================
echo.

:: Check Admin Rights
net session >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Please run as Administrator!
    echo [INFO] Right-click this bat file and select "Run as administrator"
    pause
    exit /b 1
)

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

:: Step 1: Check IIS Installation
echo [1/6] Checking IIS installation...
sc query W3SVC >nul 2>&1
if errorlevel 1 (
    echo [INFO] IIS not installed. Installing...
    dism /online /enable-feature /featurename:IIS-WebServerRole /all /norestart
    dism /online /enable-feature /featurename:IIS-WebServerManagementTools /all /norestart
    dism /online /enable-feature /featurename:IIS-ManagementConsole /all /norestart
    echo [OK] IIS installed.
) else (
    echo [OK] IIS is already installed.
)

:: Step 2: Check URL Rewrite Module
echo [2/6] Checking URL Rewrite module...
if exist "%WINDIR%\System32\inetsrv\rewrite.dll" (
    echo [OK] URL Rewrite module is installed.
) else (
    echo [WARN] URL Rewrite module NOT found.
    echo [WARN] Please download and install from:
    echo        https://www.iis.net/downloads/microsoft/url-rewrite
    echo [INFO] After installation, run this script again.
    echo.
    start https://www.iis.net/downloads/microsoft/url-rewrite
    pause
    exit /b 1
)

:: Step 3: Check ARR Module
echo [3/6] Checking ARR (Application Request Routing) module...
%WINDIR%\System32\inetsrv\appcmd.exe list modules | findstr /i "ApplicationRequestRouting" >nul 2>&1
if errorlevel 1 (
    echo [WARN] ARR module NOT found.
    echo [WARN] Please download and install from:
    echo        https://www.iis.net/downloads/microsoft/application-request-routing
    echo [INFO] After installation, run this script again.
    echo.
    start https://www.iis.net/downloads/microsoft/application-request-routing
    pause
    exit /b 1
) else (
    echo [OK] ARR module is installed.
)

:: Step 4: Create IIS Site Directory
echo [4/6] Creating IIS site directory...
set "IIS_SITE_DIR=C:\inetpub\wwwroot\FabTwin"
if not exist "%IIS_SITE_DIR%" mkdir "%IIS_SITE_DIR%"

:: Copy frontend dist to IIS directory
if exist "frontend\dist" (
    echo [INFO] Copying frontend files to IIS directory...
    xcopy /E /I /Y "frontend\dist\*" "%IIS_SITE_DIR%\" >nul
    echo [OK] Frontend files copied.
) else (
    echo [WARN] frontend\dist not found.
    echo [WARN] Please run 'npm run build' in frontend folder first.
)

:: Create web.config with reverse proxy and Windows Auth
echo [INFO] Creating web.config...
(
echo ^<?xml version="1.0" encoding="UTF-8"?^>
echo ^<configuration^>
echo   ^<system.webServer^>
echo     ^<security^>
echo       ^<authentication^>
echo         ^<anonymousAuthentication enabled="false" /^>
echo         ^<windowsAuthentication enabled="true"^>
echo           ^<providers^>
echo             ^<add value="Negotiate" /^>
echo             ^<add value="NTLM" /^>
echo           ^</providers^>
echo         ^</windowsAuthentication^>
echo       ^</authentication^>
echo     ^</security^>
echo     ^<rewrite^>
echo       ^<rules^>
echo         ^<rule name="ReverseProxyInboundRule" stopProcessing="true"^>
echo           ^<match url="^(.*)$" /^>
echo           ^<conditions^>
echo             ^<add input="{REQUEST_FILENAME}" matchType="IsFile" negate="true" /^>
echo             ^<add input="{REQUEST_FILENAME}" matchType="IsDirectory" negate="true" /^>
echo           ^</conditions^>
echo           ^<action type="Rewrite" url="http://127.0.0.1:8000/{R:1}" /^>
echo         ^</rule^>
echo       ^</rules^>
echo       ^<outboundRules^>
echo         ^<rule name="ReverseProxyOutboundRule" preCondition="ResponseIsHtml"^>
echo           ^<match filterByTags="A, Form, Img" pattern="^http://127\.0\.0\.1:8000/(.*)$" /^>
echo           ^<action type="Rewrite" value="/{R:1}" /^>
echo         ^</rule^>
echo       ^</outboundRules^>
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
echo [OK] web.config created.

:: Step 5: Create IIS Application Pool
echo [5/6] Creating IIS Application Pool...
%WINDIR%\System32\inetsrv\appcmd.exe add apppool /name:FabTwinAppPool /managedRuntimeVersion:"" /managedPipelineMode:Integrated >nul 2>&1
if errorlevel 1 (
    echo [INFO] AppPool already exists, updating...
    %WINDIR%\System32\inetsrv\appcmd.exe set apppool /apppool.name:FabTwinAppPool /managedRuntimeVersion:"" >nul
)
echo [OK] Application Pool created/updated.

:: Step 6: Create IIS Site
echo [6/6] Creating IIS Site...
%WINDIR%\System32\inetsrv\appcmd.exe add site /name:FabTwin /bindings:http/*:80: /physicalPath:"%IIS_SITE_DIR%" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Site already exists, updating...
    %WINDIR%\System32\inetsrv\appcmd.exe set site /site.name:FabTwin /bindings:http/*:80: >nul
    %WINDIR%\System32\inetsrv\appcmd.exe set app /app.name:FabTwin/ /applicationPool:FabTwinAppPool >nul
) else (
    %WINDIR%\System32\inetsrv\appcmd.exe set app /app.name:FabTwin/ /applicationPool:FabTwinAppPool >nul
)
echo [OK] IIS Site created/updated.

:: Enable Windows Authentication at site level
echo [INFO] Enabling Windows Authentication...
%WINDIR%\System32\inetsrv\appcmd.exe set config "FabTwin" -section:system.webServer/security/authentication/windowsAuthentication /enabled:"True" /commit:apphost >nul
%WINDIR%\System32\inetsrv\appcmd.exe set config "FabTwin" -section:system.webServer/security/authentication/anonymousAuthentication /enabled:"False" /commit:apphost >nul
echo [OK] Windows Authentication enabled.

:: Enable Proxy in ARR
echo [INFO] Enabling ARR Proxy...
%WINDIR%\System32\inetsrv\appcmd.exe set config -section:system.webServer/proxy /enabled:"True" /commit:apphost >nul 2>&1
echo [OK] ARR Proxy enabled.

:: Start IIS Site
echo [INFO] Starting IIS Site...
iisreset /start >nul
%WINDIR%\System32\inetsrv\appcmd.exe start site /site.name:FabTwin >nul 2>&1
echo [OK] IIS Site started.

echo.
echo ================================================================
echo  Deployment Complete!
echo ================================================================
echo.
echo [INFO] Access URL: http://%%COMPUTERNAME%% or http://this-server-ip
echo [INFO] Backend must be running on port 8000
echo [INFO] Windows Auth: Users will use their own Windows account
echo.
echo [NEXT STEPS]
echo 1. Make sure backend is running: .\start_backend.bat
echo 2. Open browser and visit http://%%COMPUTERNAME%%
echo 3. Login with your Windows domain account
echo.
echo ================================================================
pause
