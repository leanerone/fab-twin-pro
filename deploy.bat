@echo off
chcp 65001 >nul
title FabTwin 一键部署

echo ================================================
echo          FabTwin 半导体数字孪生部署脚本
echo ================================================
echo.
echo 说明：此脚本用于在公司内网环境一键部署前后端服务
echo 环境要求：Python 3.10+ / Node.js 16+ / Redis(可选)
echo.

set "BASE_DIR=%~dp0"
set "BACKEND_DIR=%BASE_DIR%backend"
set "FRONTEND_DIR=%BASE_DIR%frontend"

echo [1/4] 检查环境...

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: 未找到 Python，请先安装 Python 3.10+
    pause
    exit /b 1
)

node --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: 未找到 Node.js，请先安装 Node.js 16+
    pause
    exit /b 1
)

echo OK: Python 和 Node.js 环境已就绪
echo.

echo [2/4] 部署后端服务...

if not exist "%BACKEND_DIR%\venv" (
    echo 创建 Python 虚拟环境...
    cd /d "%BACKEND_DIR%"
    python -m venv venv
    if errorlevel 1 (
        echo ERROR: 创建虚拟环境失败
        pause
        exit /b 1
    )
)

echo 安装后端依赖...
cd /d "%BACKEND_DIR%"
venv\Scripts\pip.exe install -r requirements.txt -q
if errorlevel 1 (
    echo WARNING: pip 安装可能有部分失败（内网环境），继续尝试启动...
)

echo 初始化数据库...
venv\Scripts\python.exe -c "from database import init_db; init_db(); print('数据库初始化完成')"

echo.
echo [3/4] 部署前端服务...

cd /d "%FRONTEND_DIR%"
if not exist "node_modules" (
    echo 安装前端依赖...
    npm install -q
    if errorlevel 1 (
        echo WARNING: npm 安装可能有部分失败，继续尝试构建...
    )
)

echo 构建前端...
npm run build -q
if errorlevel 1 (
    echo WARNING: 前端构建可能有问题，请检查
)

echo.
echo [4/4] 启动服务...
echo.
echo 后端服务: http://localhost:8001
echo 前端服务: http://localhost:5173
echo API文档:  http://localhost:8001/docs
echo.
echo 按任意键启动后端服务...
pause >nul

echo 启动后端服务...
start "" "%BACKEND_DIR%\venv\Scripts\python.exe" "%BACKEND_DIR%\main.py"

echo 等待后端启动...
timeout /t 5 /nobreak >nul

echo 启动前端服务...
start "" "%FRONTEND_DIR%\node_modules\.bin\vite.cmd"

echo.
echo 服务已启动！请打开浏览器访问 http://localhost:5173
echo.
echo 停止服务方法：关闭弹出的命令行窗口
pause