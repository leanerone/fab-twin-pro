@echo off
setlocal enabledelayedexpansion

echo ================================================================
echo  FabTwin IIS Diagnostic
echo ================================================================
echo.

echo --- [1] FabTwin Site Status ---
%WINDIR%\System32\inetsrv\appcmd.exe list site /name:FabTwin
echo.

echo --- [2] FabTwin Site Bindings ---
%WINDIR%\System32\inetsrv\appcmd.exe list site /name:FabTwin /text:bindings
echo.

echo --- [3] All Sites on Port 80 ---
%WINDIR%\System32\inetsrv\appcmd.exe list site /text:bindings | findstr ":80:"
echo.

echo --- [4] FabTwin Physical Path ---
%WINDIR%\System32\inetsrv\appcmd.exe list vdir /vdir.name:FabTwin/ /text:physicalPath
echo.

echo --- [5] Check index.html exists ---
if exist "C:\inetpub\wwwroot\FabTwin\index.html" (
    echo [OK] index.html exists
    dir "C:\inetpub\wwwroot\FabTwin\index.html" | findstr "index.html"
) else (
    echo [ERROR] index.html NOT found at C:\inetpub\wwwroot\FabTwin\
)
echo.

echo --- [6] Check web.config ---
if exist "C:\inetpub\wwwroot\FabTwin\web.config" (
    echo [OK] web.config exists
    type "C:\inetpub\wwwroot\FabTwin\web.config"
) else (
    echo [WARN] web.config NOT found
)
echo.

echo --- [7] Test local backend ---
curl -s http://127.0.0.1:8002/api/health >nul 2>&1
if errorlevel 1 (
    echo [WARN] Backend NOT running on port 8002
) else (
    echo [OK] Backend is running on port 8002
)
echo.

echo ================================================================
echo  Done. Report any ERROR lines above.
echo ================================================================
pause
