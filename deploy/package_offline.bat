@echo off
title FabTwin Package Offline Deploy

REM ================================================================
REM FabTwin Offline Deployment Packaging Script
REM Usage: Prepare complete offline deploy package on internet-connected machine
REM Output: fabtwin-deploy-YYYYMMDD.zip
REM
REM IMPORTANT: English only to avoid encoding issues on Windows Server
REM ================================================================

setlocal enabledelayedexpansion

REM SCRIPT_DIR=deploy 目录（找 deploy 脚本），BASE_DIR=项目根（找 backend/frontend/sql），脚本已移至 deploy 子目录
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
pushd "%SCRIPT_DIR%\.."
set "BASE_DIR=%CD%"
popd
set "DEPLOY_DIR=%SCRIPT_DIR%\fabtwin-offline-deploy"

REM Format date as YYYYMMDD
for /f "tokens=2 delims==" %%a in ('wmic OS Get localdatetime /value 2^>nul') do set "ldt=%%a"
set "DATE_STAMP=%ldt:~0,4%%ldt:~4,2%%ldt:~6,2%"
set "ZIP_FILE=%BASE_DIR%\fabtwin-deploy-%DATE_STAMP%.zip"

echo ================================================================
echo  FabTwin Offline Deploy Packaging
echo ================================================================
echo.
echo Output dir: %DEPLOY_DIR%
echo Output ZIP: %ZIP_FILE%
echo.

REM Clean old
if exist "%DEPLOY_DIR%" rmdir /s /q "%DEPLOY_DIR%"
if exist "%ZIP_FILE%" del /q "%ZIP_FILE%"
mkdir "%DEPLOY_DIR%"

echo [1/8] Copying backend code...
mkdir "%DEPLOY_DIR%\backend"
xcopy "%BASE_DIR%\backend\*.py" "%DEPLOY_DIR%\backend\" /Y /Q >nul
xcopy "%BASE_DIR%\backend\*.txt" "%DEPLOY_DIR%\backend\" /Y /Q >nul
xcopy "%BASE_DIR%\backend\routers" "%DEPLOY_DIR%\backend\routers\" /E /I /Y /Q >nul
xcopy "%BASE_DIR%\backend\services" "%DEPLOY_DIR%\backend\services\" /E /I /Y /Q >nul
if exist "%DEPLOY_DIR%\backend\__pycache__" rmdir /s /q "%DEPLOY_DIR%\backend\__pycache__"

echo [2/8] Copying frontend code...
mkdir "%DEPLOY_DIR%\frontend"
xcopy "%BASE_DIR%\frontend\src" "%DEPLOY_DIR%\frontend\src\" /E /I /Y /Q >nul
xcopy "%BASE_DIR%\frontend\public" "%DEPLOY_DIR%\frontend\public\" /E /I /Y /Q >nul
copy /Y "%BASE_DIR%\frontend\package.json" "%DEPLOY_DIR%\frontend\" >nul
copy /Y "%BASE_DIR%\frontend\vite.config.js" "%DEPLOY_DIR%\frontend\" >nul
copy /Y "%BASE_DIR%\frontend\index.html" "%DEPLOY_DIR%\frontend\" >nul

echo [3/8] Copying SQL scripts...
mkdir "%DEPLOY_DIR%\sql"
copy /Y "%BASE_DIR%\sql\*.sql" "%DEPLOY_DIR%\sql\" >nul

echo [4/8] Copying deploy scripts...
copy /Y "%SCRIPT_DIR%\deploy.bat" "%DEPLOY_DIR%\" >nul
copy /Y "%SCRIPT_DIR%\start-dev.bat" "%DEPLOY_DIR%\" >nul
copy /Y "%SCRIPT_DIR%\start_backend.bat" "%DEPLOY_DIR%\" >nul
copy /Y "%SCRIPT_DIR%\init_db.bat" "%DEPLOY_DIR%\" >nul
copy /Y "%SCRIPT_DIR%\create_user.bat" "%DEPLOY_DIR%\" >nul 2>nul
copy /Y "%SCRIPT_DIR%\create_user.sql" "%DEPLOY_DIR%\" >nul 2>nul

echo [5/8] Checking backend deps...
cd /d "%BASE_DIR%\backend"
if not exist "venv" (
    echo Creating venv...
    python -m venv venv
)
echo Installing backend deps (online download for offline use)...
venv\Scripts\pip.exe install -r requirements.txt -q
echo Downloading pip wheels...
mkdir "%DEPLOY_DIR%\backend\wheels"
venv\Scripts\pip.exe download -r requirements.txt -d "%DEPLOY_DIR%\backend\wheels" -q
if errorlevel 1 (
    echo WARNING: some packages failed to download, may need manual install on intranet
)

echo [6/8] Checking frontend deps...
cd /d "%BASE_DIR%\frontend"
if not exist "node_modules" (
    echo Installing frontend deps...
    cmd /c "npm install -q"
)
echo Building frontend...
cmd /c "npm run build"
if errorlevel 1 (
    echo WARNING: frontend build failed, need manual build on intranet
) else (
    echo Copying build output...
    mkdir "%DEPLOY_DIR%\frontend\dist"
    xcopy "%BASE_DIR%\frontend\dist\*" "%DEPLOY_DIR%\frontend\dist\" /E /I /Y /Q >nul
)

echo [7/8] Copying node_modules (optional)...
if exist "%BASE_DIR%\frontend\node_modules" (
    mkdir "%DEPLOY_DIR%\frontend\node_modules"
    xcopy "%BASE_DIR%\frontend\node_modules" "%DEPLOY_DIR%\frontend\node_modules\" /E /I /Y /Q >nul
    echo node_modules included (skip npm install on deploy)
) else (
    echo WARNING: node_modules not found, need npm install on intranet
)

echo [8/8] Generating README...
(
echo # FabTwin Offline Deploy Package
echo.
echo Generated: %DATE_STAMP%
echo.
echo ## Contents
echo - backend/         Backend Python code + wheels offline packages
echo - frontend/        Frontend code + dist build + node_modules
echo - sql/             Database init SQL
echo - deploy.bat       One-click deploy script
echo - start-dev.bat    Dev start script
echo - start_backend.bat Production start script
echo - init_db.bat      DB init script
echo - create_user.bat  Oracle user creation script
echo.
echo ## Deploy Steps
echo 1. Extract this package to target dir
echo 2. Run create_user.bat to create Oracle user (needs sysdba)
echo    Or ask DBA team to run create_user.sql
echo 3. Run init_db.bat to init schema
echo    Or ask DBA team to run sql/init_oracle_db.sql via Aqua Data Studio
echo 4. Run deploy.bat to one-click start frontend and backend
echo 5. Open browser: http://localhost:5173
echo.
echo ## For Oracle 10g/11g
echo Set ORACLE_CLIENT_DIR env var to Instant Client path before starting
echo   set ORACLE_CLIENT_DIR=C:\oracle\instantclient_19_x
echo.
echo ## See deploy-sop.md for details
) > "%DEPLOY_DIR%\README.md"

REM Copy SOP doc
if exist "%BASE_DIR%\docs\deploy-sop.md" (
    copy /Y "%BASE_DIR%\docs\deploy-sop.md" "%DEPLOY_DIR%\" >nul
)

REM Zip
echo.
echo Packaging ZIP...
powershell -Command "Compress-Archive -Path '%DEPLOY_DIR%\*' -DestinationPath '%ZIP_FILE%' -Force"
if errorlevel 1 (
    echo WARNING: ZIP packaging failed, use %DEPLOY_DIR% directly
) else (
    echo.
    echo ================================================================
    echo  Packaging complete!
    echo ================================================================
    echo  ZIP: %ZIP_FILE%
    echo  Dir: %DEPLOY_DIR%
    echo.
    echo  Copy ZIP to intranet prod server, extract, run deploy.bat
)

pause
endlocal
