@echo off
setlocal
title FabTwin IIS NT Auth Final Deployment
echo ================================================================
echo  FabTwin IIS NT Auth Final Deployment
echo ================================================================
echo.
echo  FINAL SOLUTION:
echo    1. IIS handles Windows Authentication
echo    2. ASP file returns LOGON_USER
echo    3. Frontend reads username from ASP and sends to backend
echo    4. No reverse proxy needed for auth!
echo.
echo  REQUIREMENTS:
echo    - Run as Administrator
echo    - Windows Authentication feature installed
echo    - ASP feature installed (for get_user.asp)
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

set "SCRIPT_DIR=%~dp0"

echo.
echo [2/8] Checking IIS installation...
if not exist "%windir%\system32\inetsrv\appcmd.exe" (
    echo [ERROR] IIS not installed!
    pause
    exit /b 1
)
echo [OK] IIS is installed

echo.
echo [3/8] Checking ASP feature...
reg query "HKLM\SOFTWARE\Microsoft\InetStp\Components" /v "ASP" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing ASP feature...
    dism /online /enable-feature /featurename:IIS-ASP /all >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Failed to install ASP feature!
        pause
        exit /b 1
    )
    echo [OK] ASP feature installed
) else (
    echo [OK] ASP feature installed
)

echo.
echo [4/8] Checking Windows Authentication feature...
reg query "HKLM\SOFTWARE\Microsoft\InetStp\Components" /v "WindowsAuthentication" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing Windows Authentication...
    dism /online /enable-feature /featurename:IIS-WindowsAuthentication /all >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Failed to install Windows Auth!
        pause
        exit /b 1
    )
    echo [OK] Windows Authentication installed
) else (
    echo [OK] Windows Authentication feature installed
)

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
echo [6/8] Copying get_user.asp (returns Windows username)...
copy "%SCRIPT_DIR%\get_user.asp" "%IIS_SITE_DIR%\get_user.asp" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Failed to copy get_user.asp!
    pause
    exit /b 1
)
echo [OK] get_user.asp copied

echo.
echo [7/8] Creating web.config...
(
echo ^<?xml version="1.0" encoding="UTF-8"?^>
echo ^<configuration^>
echo   ^<system.webServer^>
echo     ^<security^>
echo       ^<authentication^>
echo         ^<anonymousAuthentication enabled="false" /^>
echo         ^<windowsAuthentication enabled="true" /^>
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
echo             ^<add input="{URL}" pattern="^/api/" negate="true" /^>
echo             ^<add input="{URL}" pattern="^/ws/" negate="true" /^>
echo             ^<add input="{URL}" pattern="^/get_user.asp" negate="true" /^>
echo           ^</conditions^>
echo           ^<action type="Rewrite" url="index.html" /^>
echo         ^</rule^>
echo       ^</rules^>
echo     ^</rewrite^>
echo   ^</system.webServer^>
echo ^</configuration^>
) > "%IIS_SITE_DIR%\web.config"
echo [OK] web.config created

echo.
echo [8/8] Configuring IIS site...
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

%windir%\system32\inetsrv\appcmd.exe set config -section:system.webServer/proxy /enabled:"true" >nul 2>&1
echo [OK] ARR Proxy enabled

%windir%\system32\inetsrv\appcmd.exe start site "FabTwin" >nul 2>&1
echo [OK] FabTwin site started

echo.
echo ================================================================
echo  Deployment Complete!
echo ================================================================
echo.
echo  Auth Mode: Windows Authentication (ASP bridge)
echo  URL:       http://SERVER-IP (port 80)
echo.
echo  HOW IT WORKS:
echo    1. Frontend calls /get_user.asp (IIS handles auth)
echo    2. get_user.asp returns LOGON_USER via IIS
echo    3. Frontend sends username to /api/auth/login-windows
echo    4. Backend creates session for this user
echo.
echo  TROUBLESHOOTING:
echo    - If 401: Check Windows Auth is installed
echo    - If 500: Check ASP feature is installed
echo    - If login fails: Check get_user.asp returns correct user
echo.
pause
endlocal