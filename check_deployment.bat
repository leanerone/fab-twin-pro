@echo off
setlocal

echo ================================================================
echo  FabTwin Deployment Diagnostic Tool
echo ================================================================
echo.

:: ================================================================
:: Section 1: Check Backend Status
:: ================================================================
echo --- [1/4] Backend Service Status ---
echo.

netstat -ano | findstr ":8002 " | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo [OK] Backend is running on port 8002
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8002 " ^| findstr "LISTENING"') do (
        echo [INFO] PID: %%a
        for /f "tokens=1" %%b in ('tasklist /FI "PID eq %%a" /FO CSV ^| findstr /v "ImageName"') do (
            echo [INFO] Process: %%b
        )
    )
) else (
    echo [ERROR] Backend is NOT running on port 8002
    echo [INFO] Please run: .\start_backend.bat
)

echo.
echo Testing backend API...
powershell -Command "try { $r = Invoke-WebRequest -Uri 'http://localhost:8002/health' -UseBasicParsing -TimeoutSec 5; Write-Host '[OK] Health check passed:' $r.StatusCode } catch { Write-Host '[ERROR] API not reachable:' $_.Exception.Message }"
echo.

:: ================================================================
:: Section 2: Check IIS Configuration
:: ================================================================
echo --- [2/4] IIS Configuration ---
echo.

echo [INFO] Checking IIS sites...
%WINDIR%\System32\inetsrv\appcmd.exe list sites | findstr /i "FabTwin" >nul
if not errorlevel 1 (
    %WINDIR%\System32\inetsrv\appcmd.exe list sites | findstr /i "FabTwin"
    echo [OK] FabTwin site exists
) else (
    echo [ERROR] FabTwin site NOT found
)

echo.
echo [INFO] Checking site bindings...
%WINDIR%\System32\inetsrv\appcmd.exe list sites /text:* | findstr /i "binding" | findstr /i "80" >nul
if not errorlevel 1 (
    %WINDIR%\System32\inetsrv\appcmd.exe list sites /text:* | findstr /i "FabTwin"
) else (
    echo [ERROR] No binding on port 80 found for FabTwin
)

echo.
echo [INFO] Checking URL Rewrite module...
if exist "%WINDIR%\System32\inetsrv\rewrite.dll" (
    echo [OK] URL Rewrite module is installed
) else (
    echo [ERROR] URL Rewrite module NOT installed
)

echo.
echo [INFO] Checking ARR module...
%WINDIR%\System32\inetsrv\appcmd.exe list modules | findstr /i "ApplicationRequestRouting" >nul 2>&1
if not errorlevel 1 (
    echo [OK] ARR module is installed
) else (
    echo [ERROR] ARR module NOT installed
)

echo.
echo [INFO] Checking ARR Proxy enabled...
%WINDIR%\System32\inetsrv\appcmd.exe list config -section:system.webServer/proxy /text:* | findstr /i "enabled" >nul 2>&1
if not errorlevel 1 (
    %WINDIR%\System32\inetsrv\appcmd.exe list config -section:system.webServer/proxy /text:* | findstr /i "enabled"
) else (
    echo [ERROR] ARR Proxy NOT enabled
)

:: ================================================================
:: Section 3: Check Frontend Files
:: ================================================================
echo.
echo --- [3/4] Frontend Files Status ---
echo.

set "IIS_SITE_DIR=C:\inetpub\wwwroot\FabTwin"

echo [INFO] IIS Site Directory: %IIS_SITE_DIR%
echo.

if exist "%IIS_SITE_DIR%\index.html" (
    for /f "tokens=3" %%a in ('dir "%IIS_SITE_DIR%\index.html" ^| findstr "index.html"') do set "SIZE=%%a"
    echo [OK] index.html exists (%SIZE% bytes)
) else (
    echo [ERROR] index.html NOT found in IIS directory!
)

echo.

if exist "%IIS_SITE_DIR%\assets" (
    for /f %%a in ('dir "%IIS_SITE_DIR%\assets" /b ^| find /c /v ""') do set "FILES=%%a"
    echo [OK] assets directory exists (%FILES% files)
) else (
    echo [ERROR] assets directory NOT found!
)

echo.

if exist "%IIS_SITE_DIR%\web.config" (
    echo [OK] web.config exists
    echo.
    echo [INFO] web.config content:
    type "%IIS_SITE_DIR%\web.config"
) else (
    echo [ERROR] web.config NOT found!
)

echo.

:: ================================================================
:: Section 4: Check API Proxy
:: ================================================================
echo --- [4/4] API Proxy Test ---
echo.

echo [INFO] Testing API through IIS (port 80)...
powershell -Command "try { $r = Invoke-WebRequest -Uri 'http://localhost/api/auth/login' -Method POST -UseBasicParsing -TimeoutSec 5; Write-Host '[OK] API proxy works:' $r.StatusCode } catch { Write-Host '[ERROR] API proxy failed:' $_.Exception.Message }"

echo.

echo ================================================================
echo  Diagnostic Complete
echo ================================================================
echo.
echo [NEXT STEPS]
echo 1. If backend not running: run .\start_backend.bat
echo 2. If IIS files missing: run .\deploy_iis.bat again
echo 3. If API proxy fails: check web.config rewrite rules
echo 4. If still IIS welcome page: check port 80 conflicts
echo.
pause

endlocal