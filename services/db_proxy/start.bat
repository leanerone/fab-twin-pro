@echo off
REM FabTwin DB Proxy 启动脚本
REM 部署在 FabTwin 后端同一台 server 上

cd /d "%~dp0"

REM 加载 .env 环境变量
if exist .env (
    for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
        set "%%a=%%b"
    )
)

echo ========================================
echo  FabTwin DB Proxy 启动
echo  Oracle: %ORACLE_HOST%:%ORACLE_PORT%/%ORACLE_SERVICE%
echo  Listen: 0.0.0.0:%DB_PROXY_PORT%
echo ========================================

python main.py

pause
