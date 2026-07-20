@echo off
chcp 65001 >nul
title FabTwin 生产环境启动

REM ================================================================
REM FabTwin 生产环境启动脚本
REM 用途：在量产服务器上启动前后端服务
REM 前提：已完成 deploy.bat 部署（venv + node_modules + dist 都已就绪）
REM ================================================================

setlocal
set "BASE_DIR=%~dp0"
set "BASE_DIR=%BASE_DIR:~0,-1%"
set "BACKEND_DIR=%BASE_DIR%\backend"
set "FRONTEND_DIR=%BASE_DIR%\frontend"

echo ================================================================
echo  FabTwin 生产环境启动
echo ================================================================
echo.

REM 检查必备文件
if not exist "%BACKEND_DIR%\venv\Scripts\python.exe" (
    echo ERROR: 后端venv不存在，请先运行 deploy.bat
    pause
    exit /b 1
)

if not exist "%FRONTEND_DIR%\dist\index.html" (
    echo ERROR: 前端构建产物不存在，请先运行 deploy.bat
    pause
    exit /b 1
)

REM 检查端口占用
netstat -ano | findstr ":8002 " | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo WARNING: 端口8002已被占用，可能后端已在运行
    choice /C YN /M "是否继续启动后端（可能失败）"
    if errorlevel 2 exit /b 0
)

netstat -ano | findstr ":5173 " | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo WARNING: 端口5173已被占用，可能前端已在运行
    choice /C YN /M "是否继续启动前端（可能失败）"
    if errorlevel 2 exit /b 0
)

REM 配置环境变量（生产环境）
set "DB_TYPE=oracle"
set "SIMULATION_ENABLED=False"
set "DB_POLLER_ENABLED=True"
REM 如果不使用默认值，请取消注释并修改以下配置
REM set "ORACLE_HOST=192.168.x.x"
REM set "ORACLE_PORT=1521"
REM set "ORACLE_SERVICE=ORCLPDB"
REM set "ORACLE_USER=fabtwin"
REM set "ORACLE_PASSWORD=fabtwin"

echo [1/2] 启动后端服务 (FastAPI :8002)...
start "FabTwin Backend" cmd /k "cd /d %BACKEND_DIR% && set DB_TYPE=oracle && set SIMULATION_ENABLED=False && set DB_POLLER_ENABLED=True && venv\Scripts\python.exe main.py"

echo 等待后端启动（5秒）...
timeout /t 5 /nobreak >nul

echo [2/2] 启动前端服务 (Vite Preview :5173)...
cd /d "%FRONTEND_DIR%"
if exist "node_modules\.bin\vite.cmd" (
    start "FabTwin Frontend" cmd /k "cd /d %FRONTEND_DIR% && node_modules\.bin\vite.cmd preview --port 5173 --host"
) else (
    echo WARNING: vite.cmd 不存在，使用 npx 启动
    start "FabTwin Frontend" cmd /k "cd /d %FRONTEND_DIR% && npx vite preview --port 5173 --host"
)

echo.
echo ================================================================
echo  服务已启动！
echo ================================================================
echo  前端: http://localhost:5173
echo  后端: http://localhost:8002
echo  API文档: http://localhost:8002/docs
echo  健康检查: http://localhost:8002/health
echo ================================================================
echo.
echo 关闭对应窗口即可停止服务
echo.
pause
