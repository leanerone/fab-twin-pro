@echo off
chcp 65001 >nul
title FabTwin 一键部署

REM ================================================================
REM FabTwin 半导体数字孪生一键部署脚本
REM 用途：在内网量产服务器一键部署前后端服务
REM 流程：检查环境 → 安装依赖 → 初始化DB → 构建前端 → 启动服务
REM ================================================================

setlocal enabledelayedexpansion

set "BASE_DIR=%~dp0"
set "BASE_DIR=%BASE_DIR:~0,-1%"
set "BACKEND_DIR=%BASE_DIR%\backend"
set "FRONTEND_DIR=%BASE_DIR%\frontend"

echo ================================================================
echo          FabTwin 半导体数字孪生部署脚本
echo ================================================================
echo.
echo 部署目录: %BASE_DIR%
echo.

REM ---------- 配置生产环境变量 ----------
set "DB_TYPE=oracle"
set "SIMULATION_ENABLED=False"
set "DB_POLLER_ENABLED=True"
REM 如非默认 Oracle 配置，请取消注释并修改
REM set "ORACLE_HOST=192.168.x.x"
REM set "ORACLE_PORT=1521"
REM set "ORACLE_SERVICE=ORCLPDB"
REM set "ORACLE_USER=fabtwin"
REM set "ORACLE_PASSWORD=fabtwin"

echo [1/5] 检查环境...
echo.

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

REM ---------- [2/5] 后端依赖 ----------
echo [2/5] 部署后端服务...
echo.

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

REM 优先使用离线 wheels 包（内网环境）
if exist "wheels" (
    echo INFO: 检测到 wheels 离线包，使用离线安装
    venv\Scripts\pip.exe install --no-index --find-links wheels -r requirements.txt -q
) else (
    venv\Scripts\pip.exe install -r requirements.txt -q
)

if errorlevel 1 (
    echo WARNING: pip 安装可能有部分失败，继续尝试...
)

REM ---------- [3/5] 数据库初始化 ----------
echo.
echo [3/5] 初始化数据库...
echo.

REM 构建连接串（DB 组提供的环境变量，默认值见 config.py）
if not defined ORACLE_HOST set "ORACLE_HOST=localhost"
if not defined ORACLE_PORT set "ORACLE_PORT=1521"
if not defined ORACLE_SERVICE set "ORACLE_SERVICE=ORCLPDB"
if not defined ORACLE_USER set "ORACLE_USER=fabtwin"
if not defined ORACLE_PASSWORD set "ORACLE_PASSWORD=fabtwin"

set "CONN_STR=%ORACLE_USER%/%ORACLE_PASSWORD%@%ORACLE_HOST%:%ORACLE_PORT%/%ORACLE_SERVICE%"

REM 检查 Oracle 连接
where sqlplus >nul 2>&1
if errorlevel 1 (
    echo WARNING: 未找到 sqlplus（本机未安装 Oracle Client）
    echo 将使用 ORM create_all 创建空表（不含基础数据）
    echo 如需完整初始化（含基础数据），请:
    echo   - 由 DB 组在 DB 服务器执行 sql\init_oracle_db.sql，或
    echo   - 在本机安装 Oracle Instant Client 后重新运行 deploy.bat
    echo.
    venv\Scripts\python.exe -c "from database import init_db; init_db(); print('ORM 表结构创建完成')"
) else (
    REM 优先使用 init_oracle_db.sql 完整初始化（含基础数据）
    if exist "%BASE_DIR%\sql\init_oracle_db.sql" (
        echo INFO: 执行 sql\init_oracle_db.sql 完整初始化（含基础数据）
        echo INFO: 连接 %ORACLE_HOST%:%ORACLE_PORT%/%ORACLE_SERVICE% as %ORACLE_USER%
        sqlplus -S "%CONN_STR%" @%BASE_DIR%\sql\init_oracle_db.sql > "%BASE_DIR%\init_db.log" 2>&1
        if errorlevel 1 (
            echo WARNING: SQL 脚本执行可能有错误，请查看 init_db.log
        ) else (
            echo OK: 数据库初始化完成
        )
    ) else (
        echo WARNING: 未找到 sql\init_oracle_db.sql，使用 ORM create_all
        venv\Scripts\python.exe -c "from database import init_db; init_db(); print('ORM 表结构创建完成')"
    )
)

REM ---------- [4/5] 前端构建 ----------
echo.
echo [4/5] 部署前端服务...
echo.

cd /d "%FRONTEND_DIR%"

REM 如已有 dist 跳过构建
if exist "dist\index.html" (
    echo INFO: 已存在 dist 构建产物，跳过构建
) else (
    if not exist "node_modules" (
        echo 安装前端依赖...
        cmd /c "npm install -q"
        if errorlevel 1 (
            echo WARNING: npm 安装失败，请检查 node_modules 是否完整
        )
    )

    echo 构建前端...
    REM 使用 vite.cmd 直接调用，绕过 PowerShell 执行策略
    if exist "node_modules\.bin\vite.cmd" (
        cmd /c "node_modules\.bin\vite.cmd build"
    ) else (
        cmd /c "npm run build"
    )
    if errorlevel 1 (
        echo ERROR: 前端构建失败
        pause
        exit /b 1
    )
)

REM ---------- [5/5] 启动服务 ----------
echo.
echo [5/5] 启动服务...
echo.

REM 检查端口占用
netstat -ano | findstr ":8002 " | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo WARNING: 端口 8002 已被占用，后端可能已在运行
)

netstat -ano | findstr ":5173 " | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo WARNING: 端口 5173 已被占用，前端可能已在运行
)

echo.
echo ================================================================
echo  服务信息
echo ================================================================
echo  前端:      http://localhost:5173
echo  后端 API:  http://localhost:8002
echo  API 文档:  http://localhost:8002/docs
echo  健康检查:  http://localhost:8002/health
echo ================================================================
echo.
echo 按任意键启动服务（关闭对应窗口即可停止）...
pause >nul

echo 启动后端服务...
start "FabTwin Backend" cmd /k "cd /d %BACKEND_DIR% && set DB_TYPE=oracle && set SIMULATION_ENABLED=False && set DB_POLLER_ENABLED=True && venv\Scripts\python.exe main.py"

echo 等待后端启动（5秒）...
timeout /t 5 /nobreak >nul

echo 启动前端服务（vite preview 生产模式）...
cd /d "%FRONTEND_DIR%"
if exist "node_modules\.bin\vite.cmd" (
    start "FabTwin Frontend" cmd /k "cd /d %FRONTEND_DIR% && node_modules\.bin\vite.cmd preview --port 5173 --host"
) else (
    echo WARNING: vite.cmd 不存在，尝试 npx
    start "FabTwin Frontend" cmd /k "cd /d %FRONTEND_DIR% && npx vite preview --port 5173 --host"
)

echo.
echo ================================================================
echo  服务已启动！
echo ================================================================
echo  请打开浏览器访问: http://localhost:5173
echo.
echo  默认登录：NT 自动登录 或 管理员登录 admin/admin123
echo ================================================================
echo.
pause
endlocal
