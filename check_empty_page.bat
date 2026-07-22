@echo off
setlocal
title FabTwin Empty Page Diagnostic
echo ================================================================
echo  FabTwin Empty Page Diagnostic
echo ================================================================
echo.

set "IIS_DIR=C:\inetpub\wwwroot\FabTwin"
set "URL=http://localhost"

REM Check IIS site
echo [1/6] Checking IIS site...
%windir%\system32\inetsrv\appcmd.exe list site "FabTwin" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] FabTwin site not found in IIS!
    goto end
)
echo [OK] FabTwin site exists
echo.

REM Check physical path
echo [2/6] Checking physical path...
if not exist "%IIS_DIR%" (
    echo [ERROR] Directory not found: %IIS_DIR%
    goto end
)
echo [OK] Directory exists: %IIS_DIR%
echo.

REM Check index.html
echo [3/6] Checking index.html...
if not exist "%IIS_DIR%\index.html" (
    echo [ERROR] index.html NOT found!
    goto end
)
for %%F in ("%IIS_DIR%\index.html") do set "SIZE=%%~zF"
echo [INFO] index.html size: %SIZE% bytes
if %SIZE% LSS 500 (
    echo [WARNING] index.html is too small (%SIZE% bytes), may be corrupted!
    echo [INFO] Content preview:
    type "%IIS_DIR%\index.html"
    echo.
) else (
    echo [OK] index.html looks valid
echo.

REM Check assets
echo [4/6] Checking assets directory...
if not exist "%IIS_DIR%\assets" (
    echo [ERROR] assets directory NOT found!
    goto end
)
for /f %%a in ('dir "%IIS_DIR%\assets" /b ^| find /c /v ""') do set "FILE_COUNT=%%a"
echo [OK] assets directory exists (%FILE_COUNT% files)
echo.

REM Check web.config
echo [5/6] Checking web.config...
if not exist "%IIS_DIR%\web.config" (
    echo [ERROR] web.config NOT found!
    goto end
)
echo [OK] web.config exists
echo [INFO] Content:
type "%IIS_DIR%\web.config"
echo.

REM Test HTTP response
echo [6/6] Testing HTTP response...
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri '%URL%' -UseBasicParsing -TimeoutSec 10; Write-Host ('[OK] Status: ' + $r.StatusCode); Write-Host ('[INFO] Content-Length: ' + $r.RawContentLength); if ($r.Content.Length -lt 500) { Write-Host '[WARNING] Response is too small!'; Write-Host $r.Content } } catch { Write-Host ('[ERROR] ' + $_.Exception.Message) }"
echo.

REM Check browser console suggestion
echo ================================================================
echo  Diagnostic suggestions:
echo ================================================================
echo  1. Open browser DevTools (F12) -> Console tab
echo  2. Check for JS errors (red text)
echo  3. Check Network tab for 404 errors
echo  4. Try Ctrl+F5 to force refresh (bypass cache)
echo  5. Try accessing http://localhost/index.html directly
echo ================================================================

:end
echo.
pause
endlocal
