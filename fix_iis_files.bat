@echo off
setlocal

echo ================================================================
echo  Fix IIS Frontend Files
echo ================================================================
echo.

set "DIST_DIR=E:\HJQ\deploy\fab-twin-pro\frontend\dist"
set "IIS_DIR=C:\inetpub\wwwroot\FabTwin"

echo --- [1] Check dist files ---
if not exist "%DIST_DIR%\index.html" (
    echo [ERROR] dist/index.html NOT found!
    echo Please run: cd frontend ^&^& npm run build
    pause
    exit /b 1
)

echo [OK] dist/index.html exists
dir "%DIST_DIR%\index.html"

echo.
echo --- [2] Copy files to IIS ---
echo Deleting old files...
rmdir /s /q "%IIS_DIR%" >nul 2>&1
mkdir "%IIS_DIR%"

echo Copying dist files...
xcopy /E /I /Y "%DIST_DIR%\*" "%IIS_DIR%\"
if errorlevel 1 (
    echo [ERROR] Copy failed!
    pause
    exit /b 1
)

echo [OK] Files copied
echo.

echo --- [3] Verify ---
echo IIS index.html size:
dir "%IIS_DIR%\index.html" | findstr "index.html"
echo.

echo --- [4] Restart IIS site ---
%WINDIR%\System32\inetsrv\appcmd.exe stop site /site.name:FabTwin >nul
timeout /t 1 /nobreak >nul
%WINDIR%\System32\inetsrv\appcmd.exe start site /site.name:FabTwin >nul
echo [OK] FabTwin site restarted
echo.

echo ================================================================
echo  Done! Try accessing http://10.30.5.216
echo ================================================================
pause
