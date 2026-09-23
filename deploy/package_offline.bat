@echo off
REM ====================================================================
REM  FabTwin Pro - Offline Deployment Package Builder
REM  在"在线开发机"上运行，把整个项目打成可离线安装的 zip 包
REM
REM  输出:  <BASE_DIR>\fabtwin-deploy-YYYYMMDD-HHmm.zip
REM  包含:
REM    - backend/           (含 venv, wheels, main.py, routers/, services/)
REM    - frontend/          (含 dist/, node_modules/, package.json)
REM    - services/db_proxy/ (db 转抛服务 8001)
REM    - sql/               (Oracle 初始化脚本)
REM    - deploy/            (15 个脚本 + web.config + env.bat + README)
REM    - docs/              (DEPLOY_SOP.md + 集成/架构/变更记录)
REM    - docs/integration/  (Dify/n8n 工作流 + AI 集成 SOP)
REM    - scripts/archive/get_user.asp (IIS Windows Auth 桥接)
REM
REM  注意: 此脚本必须在联网机器上运行（需要 pip download 拉 wheels）
REM        离线机只需要解压 zip 即可，无需联网
REM ====================================================================

setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

REM ---- 路径推算 ----
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
pushd "%SCRIPT_DIR%\.."
set "BASE_DIR=%CD%"
popd

echo ============================================================
echo  FabTwin Pro - 离线部署包打包脚本
echo  BASE_DIR: %BASE_DIR%
echo ============================================================
echo.

REM ---- 前置检查 ----
if not exist "%BASE_DIR%\backend\main.py" (
    echo [ERROR] backend\main.py 不存在，请确认在 fab-twin-pro 项目根运行
    pause
    exit /b 1
)

REM ---- 生成时间戳 ----
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value 2^>nul ^| find "="') do set "LDT=%%I"
set "DATE_STAMP=%LDT:~0,8%-%LDT:~8,4%"
set "DEPLOY_DIR=%BASE_DIR%\fabtwin-offline-%DATE_STAMP%"
set "ZIP_FILE=%BASE_DIR%\fabtwin-deploy-%DATE_STAMP%.zip"

echo [INFO] 输出目录: %DEPLOY_DIR%
echo [INFO] 压缩包:     %ZIP_FILE%
echo.

REM ---- 清理上次残留 ----
if exist "%DEPLOY_DIR%" rmdir /s /q "%DEPLOY_DIR%"
if exist "%ZIP_FILE%" del /f /q "%ZIP_FILE%"
mkdir "%DEPLOY_DIR%"

REM ============================================================
REM [1/8] 打包 backend/（源码 + 依赖 + wheels）
REM ============================================================
echo [1/8] 打包 backend/...
mkdir "%DEPLOY_DIR%\backend"
xcopy "%BASE_DIR%\backend\*.py" "%DEPLOY_DIR%\backend\" /Y /Q >nul
xcopy "%BASE_DIR%\backend\*.txt" "%DEPLOY_DIR%\backend\" /Y /Q >nul
xcopy "%BASE_DIR%\backend\routers" "%DEPLOY_DIR%\backend\routers\" /E /I /Y /Q >nul
xcopy "%BASE_DIR%\backend\services" "%DEPLOY_DIR%\backend\services\" /E /I /Y /Q >nul
if exist "%DEPLOY_DIR%\backend\__pycache__" rmdir /s /q "%DEPLOY_DIR%\backend\__pycache__"
if exist "%DEPLOY_DIR%\backend\.pytest_cache" rmdir /s /q "%DEPLOY_DIR%\backend\.pytest_cache"
echo       backend 源码完成。

REM ---- 拉 wheels（需联网）----
echo       下载 Python 依赖 wheels（联网）...
mkdir "%DEPLOY_DIR%\backend\wheels"
if exist "%BASE_DIR%\backend\venv\Scripts\pip.exe" (
    "%BASE_DIR%\backend\venv\Scripts\pip.exe" download -r "%BASE_DIR%\backend\requirements.txt" -d "%DEPLOY_DIR%\backend\wheels" --quiet --disable-pip-version-check
) else (
    echo       [WARN] backend\venv 不存在，使用系统 pip
    pip download -r "%BASE_DIR%\backend\requirements.txt" -d "%DEPLOY_DIR%\backend\wheels" --quiet --disable-pip-version-check
)
echo       wheels 完成。

REM ============================================================
REM [2/8] 打包 frontend/（dist + src + node_modules）
REM ============================================================
echo [2/8] 打包 frontend/...
mkdir "%DEPLOY_DIR%\frontend"
xcopy "%BASE_DIR%\frontend\src" "%DEPLOY_DIR%\frontend\src\" /E /I /Y /Q >nul
xcopy "%BASE_DIR%\frontend\public" "%DEPLOY_DIR%\frontend\public\" /E /I /Y /Q >nul
copy /Y "%BASE_DIR%\frontend\package.json" "%DEPLOY_DIR%\frontend\" >nul
copy /Y "%BASE_DIR%\frontend\vite.config.js" "%DEPLOY_DIR%\frontend\" >nul
copy /Y "%BASE_DIR%\frontend\index.html" "%DEPLOY_DIR%\frontend\" >nul
copy /Y "%BASE_DIR%\frontend\package-lock.json" "%DEPLOY_DIR%\frontend\" >nul

REM ---- 如果 dist 已构建则打包；否则构建一次 ----
if exist "%BASE_DIR%\frontend\dist\index.html" (
    echo       使用已构建的 frontend\dist\
    mkdir "%DEPLOY_DIR%\frontend\dist"
    xcopy "%BASE_DIR%\frontend\dist\*" "%DEPLOY_DIR%\frontend\dist\" /E /I /Y /Q >nul
) else (
    echo       [INFO] frontend\dist 不存在，在线构建中...
    pushd "%BASE_DIR%\frontend"
    call npm install --silent --no-audit --no-fund 2>nul
    call npm run build
    popd
    if exist "%BASE_DIR%\frontend\dist\index.html" (
        mkdir "%DEPLOY_DIR%\frontend\dist"
        xcopy "%BASE_DIR%\frontend\dist\*" "%DEPLOY_DIR%\frontend\dist\" /E /I /Y /Q >nul
    ) else (
        echo       [WARN] frontend 构建失败，dist 不会包含在包内。请手动跑 npm run build 后再打包。
    )
)

REM ---- 打包 node_modules（若存在）----
if exist "%BASE_DIR%\frontend\node_modules" (
    echo       打包 frontend\node_modules\
    mkdir "%DEPLOY_DIR%\frontend\node_modules"
    xcopy "%BASE_DIR%\frontend\node_modules" "%DEPLOY_DIR%\frontend\node_modules\" /E /I /Y /Q >nul 2>nul
) else (
    echo       [INFO] frontend\node_modules 不存在；离线机需联网跑一次 npm install
)
echo       frontend 完成。

REM ============================================================
REM [3/8] 打包 services/db_proxy/
REM ============================================================
echo [3/8] 打包 services\db_proxy/...
mkdir "%DEPLOY_DIR%\services\db_proxy"
copy /Y "%BASE_DIR%\services\db_proxy\main.py" "%DEPLOY_DIR%\services\db_proxy\" >nul
copy /Y "%BASE_DIR%\services\db_proxy\requirements.txt" "%DEPLOY_DIR%\services\db_proxy\" >nul
copy /Y "%BASE_DIR%\services\db_proxy\start.bat" "%DEPLOY_DIR%\services\db_proxy\" >nul
copy /Y "%BASE_DIR%\services\db_proxy\.env.example" "%DEPLOY_DIR%\services\db_proxy\" >nul
echo       db_proxy 完成（端口 8001）。

REM ============================================================
REM [4/8] 打包 sql/
REM ============================================================
echo [4/8] 打包 sql/...
mkdir "%DEPLOY_DIR%\sql"
copy /Y "%BASE_DIR%\sql\*.sql" "%DEPLOY_DIR%\sql\" >nul
echo       sql 完成（%DEPLOY_DIR%\sql\）。

REM ============================================================
REM [5/8] 打包 deploy/（所有启动脚本 + 配置）
REM ============================================================
echo [5/8] 打包 deploy/...
mkdir "%DEPLOY_DIR%\deploy"
copy /Y "%BASE_DIR%\deploy\package_offline.bat" "%DEPLOY_DIR%\deploy\" >nul
copy /Y "%BASE_DIR%\deploy\env.bat" "%DEPLOY_DIR%\deploy\" >nul
copy /Y "%BASE_DIR%\deploy\start-dev.bat" "%DEPLOY_DIR%\deploy\" >nul
copy /Y "%BASE_DIR%\deploy\init_db.bat" "%DEPLOY_DIR%\deploy\" >nul

REM ---- IIS 模式 ----
copy /Y "%BASE_DIR%\deploy\deploy_iis_nt_final.bat" "%DEPLOY_DIR%\deploy\" >nul
copy /Y "%BASE_DIR%\deploy\start_iis.bat" "%DEPLOY_DIR%\deploy\" >nul
copy /Y "%BASE_DIR%\deploy\start_iis.ps1" "%DEPLOY_DIR%\deploy\" >nul
copy /Y "%BASE_DIR%\deploy\web.config" "%DEPLOY_DIR%\deploy\" >nul

REM ---- 直连模式 ----
copy /Y "%BASE_DIR%\deploy\start_direct.bat" "%DEPLOY_DIR%\deploy\" >nul
copy /Y "%BASE_DIR%\deploy\start_direct.ps1" "%DEPLOY_DIR%\deploy\" >nul

REM ---- 仅后端模式 ----
copy /Y "%BASE_DIR%\deploy\start_backend.bat" "%DEPLOY_DIR%\deploy\" >nul
copy /Y "%BASE_DIR%\deploy\start_backend.ps1" "%DEPLOY_DIR%\deploy\" >nul

REM ---- AI 部署（可选）----
copy /Y "%BASE_DIR%\deploy\deploy_dify.ps1" "%DEPLOY_DIR%\deploy\" >nul
copy /Y "%BASE_DIR%\deploy\deploy_n8n.ps1" "%DEPLOY_DIR%\deploy\" >nul

REM ---- deploy 自带 README ----
copy /Y "%BASE_DIR%\deploy\README.md" "%DEPLOY_DIR%\deploy\" >nul

REM ---- scripts/archive 中的 get_user.asp + create_user ----
if exist "%BASE_DIR%\scripts\archive\get_user.asp" (
    mkdir "%DEPLOY_DIR%\scripts\archive" 2>nul
    copy /Y "%BASE_DIR%\scripts\archive\get_user.asp" "%DEPLOY_DIR%\scripts\archive\" >nul
) else (
    echo       [WARN] scripts\archive\get_user.asp 不存在，IIS 部署会失败
)
if exist "%BASE_DIR%\scripts\archive\create_user.bat" copy /Y "%BASE_DIR%\scripts\archive\create_user.bat" "%DEPLOY_DIR%\" >nul 2>nul
if exist "%BASE_DIR%\scripts\archive\create_user.sql" copy /Y "%BASE_DIR%\scripts\archive\create_user.sql" "%DEPLOY_DIR%\" >nul 2>nul
echo       deploy 完成。

REM ============================================================
REM [6/8] 打包 docs/（主 SOP + 集成 + 架构）
REM ============================================================
echo [6/8] 打包 docs/...
mkdir "%DEPLOY_DIR%\docs"
if exist "%BASE_DIR%\docs\DEPLOY_SOP.md" (
    copy /Y "%BASE_DIR%\docs\DEPLOY_SOP.md" "%DEPLOY_DIR%\docs\" >nul
) else if exist "%BASE_DIR%\docs\deploy-sop.md" (
    copy /Y "%BASE_DIR%\docs\deploy-sop.md" "%DEPLOY_DIR%\docs\DEPLOY_SOP.md" >nul
) else (
    echo       [WARN] docs\DEPLOY_SOP.md 不存在
)
if exist "%BASE_DIR%\docs\系统架构说明书.md" copy /Y "%BASE_DIR%\docs\系统架构说明书.md" "%DEPLOY_DIR%\docs\" >nul
if exist "%BASE_DIR%\docs\变更更改版记录.md" copy /Y "%BASE_DIR%\docs\变更更改版记录.md" "%DEPLOY_DIR%\docs\" >nul
if exist "%BASE_DIR%\docs\FabTwin_系统架构图.svg" copy /Y "%BASE_DIR%\docs\FabTwin_系统架构图.svg" "%DEPLOY_DIR%\docs\" >nul
if exist "%BASE_DIR%\docs\FabTwin_系统架构图.drawio" copy /Y "%BASE_DIR%\docs\FabTwin_系统架构图.drawio" "%DEPLOY_DIR%\docs\" >nul
if exist "%BASE_DIR%\docs\README.md" copy /Y "%BASE_DIR%\docs\README.md" "%DEPLOY_DIR%\docs\" >nul
echo       docs 完成。

REM ============================================================
REM [7/8] 打包 docs/integration/（Dify + n8n 工作流 + AI 集成 SOP）
REM ============================================================
echo [7/8] 打包 docs\integration/...
if exist "%BASE_DIR%\docs\integration" (
    xcopy "%BASE_DIR%\docs\integration" "%DEPLOY_DIR%\docs\integration\" /E /I /Y /Q >nul
    echo       docs\integration 完成（含 Dify 模板 + n8n 工作流 + AI 集成 SOP）。
) else (
    echo       [WARN] docs\integration 不存在
)

REM ============================================================
REM [8/8] 打包 PROJECT_STATUS.md + README.md
REM ============================================================
echo [8/8] 打包根目录 README / PROJECT_STATUS ...
if exist "%BASE_DIR%\README.md" copy /Y "%BASE_DIR%\README.md" "%DEPLOY_DIR%\" >nul
if exist "%BASE_DIR%\PROJECT_STATUS.md" copy /Y "%BASE_DIR%\PROJECT_STATUS.md" "%DEPLOY_DIR%\" >nul
if exist "%BASE_DIR%\tests\test_n8n_f1_f10.py" copy /Y "%BASE_DIR%\tests\test_n8n_f1_f10.py" "%DEPLOY_DIR%\tests\" >nul 2>nul
echo       根文档完成。

echo.
echo ============================================================
echo  生成压缩包 ...
echo ============================================================

REM ---- 找 PowerShell 压缩（统一用 Compress-Archive）----
if exist "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path '%DEPLOY_DIR%\*' -DestinationPath '%ZIP_FILE%' -Force"
) else (
    echo       [WARN] PowerShell 不存在；请手动把 %DEPLOY_DIR% 打包成 %ZIP_FILE%
)
if exist "%ZIP_FILE%" (
    echo.
    echo ============================================================
    echo  [OK] 离线包生成完成
    echo    路径: %ZIP_FILE%
    echo    解压到离线机器后，按 docs\DEPLOY_SOP.md 执行即可
    echo ============================================================
) else (
    echo.
    echo ============================================================
    echo  [ERROR] 压缩失败；%DEPLOY_DIR% 已生成，请手动压缩
    echo    目录: %DEPLOY_DIR%
    echo ============================================================
)

echo.
pause
endlocal