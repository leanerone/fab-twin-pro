@echo off
setlocal enabledelayedexpansion

echo ================================================================
echo  FabTwin IIS Detailed Diagnostic
echo ================================================================
echo.

echo --- [1] ALL Sites (including bindings) ---
%WINDIR%\System32\inetsrv\appcmd.exe list site
echo.

echo --- [2] Check FAB-IIS-Gateway bindings ---
%WINDIR%\System32\inetsrv\appcmd.exe list site /name:"FAB-IIS-Gateway"
echo.

echo --- [3] index.html content (first 20 lines) ---
echo ----------------------------------------
head -n 20 "C:\inetpub\wwwroot\FabTwin\index.html"
echo ----------------------------------------
echo.

echo --- [4] Frontend dist index.html for comparison ---
if exist "E:\HJQ\deploy\fab-twin-pro\frontend\dist\index.html" (
    echo SIZE:
    dir "E:\HJQ\deploy\fab-twin-pro\frontend\dist\index.html" | findstr "index.html"
    echo CONTENT (first 5 lines):
    head -n 5 "E:\HJQ\deploy\fab-twin-pro\frontend\dist\index.html"
) else (
    echo [ERROR] frontend\dist\index.html NOT found
)
echo.

echo --- [5] Refresh frontend files ---
echo Copying frontend dist to IIS directory...
xcopy /E /I /Y "E:\HJQ\deploy\fab-twin-pro\frontend\dist\*" "C:\inetpub\wwwroot\FabTwin\" >nul
echo Done. Checking new size...
dir "C:\inetpub\wwwroot\FabTwin\index.html" | findstr "index.html"
echo.

echo --- [6] Fix: Change FAB-IIS-Gateway to port 8081 ---
echo Checking FAB-IIS-Gateway...
%WINDIR%\System32\inetsrv\appcmd.exe list site /name:"FAB-IIS-Gateway" | findstr ":80:" >nul
if errorlevel 1 (
    echo [OK] FAB-IIS-Gateway not on port 80
) else (
    echo [FIX] Changing FAB-IIS-Gateway from port 80 to 8081...
    %WINDIR%\System32\inetsrv\appcmd.exe set site /site.name:"FAB-IIS-Gateway" /bindings:http/*:8081: >nul
    echo [OK] Done
)
echo.

echo --- [7] Verify only FabTwin on port 80 ---
echo Sites on port 80:
%WINDIR%\System32\inetsrv\appcmd.exe list site /text:bindings | findstr ":80:"
echo.

echo --- [8] Restart FabTwin ---
%WINDIR%\System32\inetsrv\appcmd.exe stop site /site.name:FabTwin >nul
timeout /t 1 /nobreak >nul
%WINDIR%\System32\inetsrv\appcmd.exe start site /site.name:FabTwin >nul
echo [OK] FabTwin restarted
echo.

echo ================================================================
echo  Done. Try accessing http://10.30.5.216 again.
echo ================================================================
pause
