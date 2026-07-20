@echo off
chcp 65001 >nul
title FabTwin 打包离线部署包

REM ================================================================
REM FabTwin 离线部署打包脚本
REM 用途：在联网环境准备完整的离线部署包，传到内网量产服务器解压即用
REM 输出：fabtwin-deploy-YYYYMMDD.zip
REM ================================================================

setlocal enabledelayedexpansion

set "BASE_DIR=%~dp0"
set "BASE_DIR=%BASE_DIR:~0,-1%"
set "DEPLOY_DIR=%BASE_DIR%\fabtwin-offline-deploy"
set "ZIP_FILE=%BASE_DIR%\fabtwin-deploy-%date:~0,4%%date:~5,2%%date:~8,2%.zip"

echo ================================================================
echo  FabTwin 离线部署打包工具
echo ================================================================
echo.
echo 输出目录: %DEPLOY_DIR%
echo 输出ZIP:  %ZIP_FILE%
echo.

REM 清理旧目录
if exist "%DEPLOY_DIR%" rmdir /s /q "%DEPLOY_DIR%"
if exist "%ZIP_FILE%" del /q "%ZIP_FILE%"
mkdir "%DEPLOY_DIR%"

echo [1/8] 复制后端代码...
mkdir "%DEPLOY_DIR%\backend"
xcopy "%BASE_DIR%\backend\*.py" "%DEPLOY_DIR%\backend\" /Y /Q >nul
xcopy "%BASE_DIR%\backend\*.txt" "%DEPLOY_DIR%\backend\" /Y /Q >nul
xcopy "%BASE_DIR%\backend\routers" "%DEPLOY_DIR%\backend\routers\" /E /I /Y /Q >nul
xcopy "%BASE_DIR%\backend\services" "%DEPLOY_DIR%\backend\services\" /E /I /Y /Q >nul
REM 排除 __pycache__, venv, .db 文件
if exist "%DEPLOY_DIR%\backend\__pycache__" rmdir /s /q "%DEPLOY_DIR%\backend\__pycache__"

echo [2/8] 复制前端代码（含源码，内网重建）...
mkdir "%DEPLOY_DIR%\frontend"
xcopy "%BASE_DIR%\frontend\src" "%DEPLOY_DIR%\frontend\src\" /E /I /Y /Q >nul
xcopy "%BASE_DIR%\frontend\public" "%DEPLOY_DIR%\frontend\public\" /E /I /Y /Q >nul
copy /Y "%BASE_DIR%\frontend\package.json" "%DEPLOY_DIR%\frontend\" >nul
copy /Y "%BASE_DIR%\frontend\vite.config.js" "%DEPLOY_DIR%\frontend\" >nul
copy /Y "%BASE_DIR%\frontend\index.html" "%DEPLOY_DIR%\frontend\" >nul

echo [3/8] 复制SQL脚本...
mkdir "%DEPLOY_DIR%\sql"
copy /Y "%BASE_DIR%\sql\*.sql" "%DEPLOY_DIR%\sql\" >nul

echo [4/8] 复制部署脚本...
copy /Y "%BASE_DIR%\deploy.bat" "%DEPLOY_DIR%\" >nul
copy /Y "%BASE_DIR%\start-dev.bat" "%DEPLOY_DIR%\" >nul
copy /Y "%BASE_DIR%\start_prod.bat" "%DEPLOY_DIR%\" >nul
copy /Y "%BASE_DIR%\init_db.bat" "%DEPLOY_DIR%\" >nul
copy /Y "%BASE_DIR%\create_user.bat" "%DEPLOY_DIR%\" >nul
copy /Y "%BASE_DIR%\create_user.sql" "%DEPLOY_DIR%\" >nul

echo [5/8] 检查后端依赖...
cd /d "%BASE_DIR%\backend"
if not exist "venv" (
    echo 创建虚拟环境...
    python -m venv venv
)
echo 安装/更新后端依赖（联网下载，打包后离线可用）...
venv\Scripts\pip.exe install -r requirements.txt -q
echo 下载pip离线包到 wheels 目录...
mkdir "%DEPLOY_DIR%\backend\wheels"
venv\Scripts\pip.exe download -r requirements.txt -d "%DEPLOY_DIR%\backend\wheels" -q
if errorlevel 1 (
    echo WARNING: 部分包下载失败，内网部署时可能需要手动安装
)

echo [6/8] 检查前端依赖...
cd /d "%BASE_DIR%\frontend"
if not exist "node_modules" (
    echo 安装前端依赖...
    npm install -q
)
echo 构建前端...
call npm run build
if errorlevel 1 (
    echo WARNING: 前端构建失败，内网部署时需要手动构建
) else (
    echo 复制构建产物到部署包...
    mkdir "%DEPLOY_DIR%\frontend\dist"
    xcopy "%BASE_DIR%\frontend\dist\*" "%DEPLOY_DIR%\frontend\dist\" /E /I /Y /Q >nul
)

REM 复制node_modules（可选，但体积较大）
echo [7/8] 复制前端node_modules（可选，便于完全离线部署）...
if exist "%BASE_DIR%\frontend\node_modules" (
    mkdir "%DEPLOY_DIR%\frontend\node_modules"
    xcopy "%BASE_DIR%\frontend\node_modules" "%DEPLOY_DIR%\frontend\node_modules\" /E /I /Y /Q >nul
    echo node_modules 已包含（部署时跳过 npm install）
) else (
    echo WARNING: node_modules 不存在，内网部署时需要 npm install
)

echo [8/8] 生成离线部署说明...
(
echo # FabTwin 离线部署包
echo.
echo 生成时间: %date% %time%
echo.
echo ## 包含内容
echo - backend/         后端Python代码 + wheels离线包
echo - frontend/        前端代码 + dist构建产物 + node_modules
echo - sql/             数据库初始化SQL
echo - deploy.bat       一键部署脚本
echo - start-dev.bat    开发启动脚本
echo - init_db.bat      数据库初始化脚本
echo - create_user.bat  Oracle用户创建脚本
echo.
echo ## 部署步骤
echo 1. 解压本包到目标目录
echo 2. 运行 create_user.bat 创建Oracle用户（需sysdba）
echo 3. 运行 init_db.bat 初始化表结构
echo 4. 运行 deploy.bat 一键启动前后端
echo 5. 访问 http://localhost:5173
echo.
echo ## 详细说明请参考 deploy-sop.md
) > "%DEPLOY_DIR%\README.md"

REM 复制SOP文档
if exist "%BASE_DIR%\docs\deploy-sop.md" (
    copy /Y "%BASE_DIR%\docs\deploy-sop.md" "%DEPLOY_DIR%\" >nul
)

REM 打包
echo.
echo 正在打包ZIP...
powershell -Command "Compress-Archive -Path '%DEPLOY_DIR%\*' -DestinationPath '%ZIP_FILE%' -Force"
if errorlevel 1 (
    echo WARNING: ZIP打包失败，可直接使用 %DEPLOY_DIR% 目录
) else (
    echo.
    echo ================================================================
    echo  打包完成！
    echo ================================================================
    echo  ZIP文件: %ZIP_FILE%
    echo  目录: %DEPLOY_DIR%
    echo.
    echo  将ZIP文件复制到内网量产服务器解压后运行 deploy.bat 即可
)

pause
