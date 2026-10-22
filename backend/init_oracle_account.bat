@echo off
chcp 65001 >nul
cd /d E:\AI\fab-twin-pro-main\backend

echo [1/2] 创建 Oracle fabtwin 应用账号（连接 XEPDB1）...
.\venv\Scripts\python.exe sql_runner.py init_app_account.sql
if errorlevel 1 (
  echo.
  echo [失败] 请检查 OracleServiceXE 服务是否已启动、1521端口是否监听。
  pause
  exit /b 1
)

echo.
echo [2/2] 检查 db_proxy 依赖（系统Python）...
python -c "import oracledb, fastapi, uvicorn" 2>nul
if errorlevel 1 (
  echo 正在安装 db_proxy 依赖（清华镜像）...
  python -m pip install -r ..\services\db_proxy\requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
) else (
  echo 依赖已就绪
)

echo.
echo === 全部完成，可以关闭本窗口 ===
pause
