@echo off
setlocal
title FabTwin IIS Windows Auth Deployment
echo ================================================================
echo  FabTwin IIS Windows Auth Deployment
echo ================================================================
echo.
echo  REQUIREMENTS:
echo    - Run as Administrator
echo    - Windows Authentication feature installed
echo    - URL Rewrite and ARR modules installed
echo.
pause
echo.

net session >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Please run as Administrator!
    pause
    exit /b 1
)
echo [OK] Running as Administrator

echo.
echo [2/8] Checking IIS installation...
if not exist "%windir%\system32\inetsrv\appcmd.exe" (
    echo [ERROR] IIS not installed!
    pause
    exit /b 1
)
echo [OK] IIS is installed

echo.
echo [3/8] Checking required modules...
reg query "HKLM\SOFTWARE\Microsoft\IIS Extensions\URL Rewrite" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] URL Rewrite module not installed!
    pause
    exit /b 1
)
echo [OK] URL Rewrite module installed

echo.
echo [4/8] Checking Windows Authentication feature...
reg query "HKLM\SOFTWARE\Microsoft\InetStp\Components" /v "WindowsAuthentication" >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Windows Authentication feature may not be installed.
    echo [INFO] Please install it via: Server Manager -> Add Roles -> Web Server -> Security -> Windows Authentication
    pause
)
echo [OK] Windows Authentication feature check done

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

echo.
echo [6/8] Creating web.config (SIMPLE version without location nodes)...
(
echo ^<?xml version="1.0" encoding="UTF-8"?^>
echo ^<configuration^>
echo   ^<system.webServer^>
echo     ^<rewrite^>
echo       ^<rules^>
echo         ^<rule name="APIProxy" stopProcessing="true"^>
echo           ^<match url="^api/(.*)" /^>
echo           ^<action type="Rewrite" url="http://127.0.0.1:8002/api/{R:1}" /^>
echo           ^<serverVariables^>
echo             ^<set name="HTTP_X_FORWARDED_USER" value="{LOGON_USER}" /^>
echo             ^<set name="HTTP_X_FORWARDED_FOR" value="{REMOTE_ADDR}" /^>
echo           ^</serverVariables^>
echo         ^</rule^>
echo         ^<rule name="WSProxy" stopProcessing="true"^>
echo           ^<match url="^ws/(.*)" /^>
echo           ^<action type="Rewrite" url="http://127.0.0.1:8002/ws/{R:1}" /^>
echo           ^<serverVariables^>
echo             ^<set name="HTTP_X_FORWARDED_USER" value="{LOGON_USER}" /^>
echo             ^<set name="HTTP_X_FORWARDED_FOR" value="{REMOTE_ADDR}" /^>
echo           ^</serverVariables^>
echo         ^</rule^>
echo         ^<rule name="SpaFallback" stopProcessing="true"^>
echo           ^<match url="^(.*)$" /^>
echo           ^<conditions^>
echo             ^<add input="{REQUEST_FILENAME}" matchType="IsFile" negate="true" /^>
echo             ^<add input="{REQUEST_FILENAME}" matchType="IsDirectory" negate="true" /^>
echo             ^<add input="{URL}" pattern="^/api/" negate="true" /^>
echo             ^<add input="{URL}" pattern="^/ws/" negate="true" /^>
echo           ^</conditions^>
echo           ^<action type="Rewrite" url="index.html" /^>
echo         ^</rule^>
echo       ^</rules^>
echo       ^<allowedServerVariables^>
echo         ^<add name="HTTP_X_FORWARDED_USER" /^>
echo         ^<add name="HTTP_X_FORWARDED_FOR" /^>
echo       ^</allowedServerVariables^>
echo     ^</rewrite^>
echo     ^<httpProtocol^>
echo       ^<customHeaders^>
echo       ^</customHeaders^>
echo     ^</httpProtocol^>
echo   ^</system.webServer^>
echo ^</configuration^>
) > "%IIS_SITE_DIR%\web.config"
echo [OK] web.config created (SIMPLE version)

echo.
echo [7/8] Configuring IIS site and authentication...

%windir%\system32\inetsrv\appcmd.exe add apppool /name:"FabTwinAppPool" /managedRuntimeVersion:"" >nul 2>&1
%windir%\system32\inetsrv\appcmd.exe set apppool "FabTwinAppPool" /processModel.identityType:"ApplicationPoolIdentity" >nul 2>&1
echo [OK] Application Pool configured

%windir%\system32\inetsrv\appcmd.exe add site /name:"FabTwin" /physicalPath:"%IIS_SITE_DIR%" /bindings:"http/*:80:" >nul 2>&1
if errorlevel 1 (
    %windir%\system32\inetsrv\appcmd.exe set site "FabTwin" /bindings:"http/*:80:" >nul 2>&1
    %windir%\system32\inetsrv\appcmd.exe set app "FabTwin/" /applicationPool:"FabTwinAppPool" >nul 2>&1
)
echo [OK] Site configured

%windir%\system32\inetsrv\appcmd.exe stop site "Default Web Site" >nul 2>&1
echo [OK] Default Web Site stopped

echo [INFO] Unlocking authentication configuration...
%windir%\system32\inetsrv\appcmd.exe unlock config -section:system.webServer/security/authentication/anonymousAuthentication >nul 2>&1
%windir%\system32\inetsrv\appcmd.exe unlock config -section:system.webServer/security/authentication/windowsAuthentication >nul 2>&1
echo [OK] Authentication sections unlocked

echo [INFO] Setting Anonymous Authentication enabled...
%windir%\system32\inetsrv\appcmd.exe set config "FabTwin" -section:system.webServer/security/authentication/anonymousAuthentication /enabled:"true" >nul 2>&1
echo [OK] Anonymous Authentication enabled

echo [INFO] Setting Windows Authentication enabled...
%windir%\system32\inetsrv\appcmd.exe set config "FabTwin" -section:system.webServer/security/authentication/windowsAuthentication /enabled:"true" >nul 2>&1
echo [OK] Windows Authentication enabled

echo [INFO] Setting Windows Auth providers...
%windir%\system32\inetsrv\appcmd.exe set config "FabTwin" -section:system.webServer/security/authentication/windowsAuthentication /+"providers.[value='Negotiate']" >nul 2>&1
%windir%\system32\inetsrv\appcmd.exe set config "FabTwin" -section:system.webServer/security/authentication/windowsAuthentication /+"providers.[value='NTLM']" >nul 2>&1
echo [OK] Windows Auth providers configured

%windir%\system32\inetsrv\appcmd.exe set config -section:system.webServer/proxy /enabled:"true" >nul 2>&1
echo [OK] ARR Proxy enabled

%windir%\system32\inetsrv\appcmd.exe set config -section:system.webServer/rewrite/allowedServerVariables /+"[name='HTTP_X_FORWARDED_USER']" >nul 2>&1
%windir%\system32\inetsrv\appcmd.exe set config -section:system.webServer/rewrite/allowedServerVariables /+"[name='HTTP_X_FORWARDED_FOR']" >nul 2>&1
echo [OK] Server variables allowed

%windir%\system32\inetsrv\appcmd.exe start site "FabTwin" >nul 2>&1
echo [OK] FabTwin site started

echo.
echo [8/8] Verifying configuration...
%windir%\system32\inetsrv\appcmd.exe list config "FabTwin" -section:system.webServer/security/authentication | findstr "enabled"

echo.
echo ================================================================
echo  Deployment Complete!
echo ================================================================
echo.
echo  Auth Mode: Mixed (Anonymous + Windows Auth)
echo  URL:       http://SERVER-IP (port 80)
echo.
echo  HOW IT WORKS:
echo    1. Site-level: Anonymous + Windows Auth both enabled
echo    2. Browser sends Windows credentials automatically (intranet)
echo    3. IIS passes {LOGON_USER} to backend via X-Forwarded-User
echo    4. If Windows Auth fails, user falls back to password login
echo.
echo  TROUBLESHOOTING:
echo    - If login fails: Check browser "Local intranet" security zone
echo    - If 401: Make sure Windows Auth feature is installed
echo    - If 500: Check Event Viewer for detailed error
echo.
pause
endlocal
