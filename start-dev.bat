@echo off
chcp 65001 >nul
echo ========================================
echo  FabTwin 半导体厂数字孪生 - 开发启动
echo ========================================
echo.

REM 启动后端
echo [1/2] 启动后端 (FastAPI :8002)...
start "FabTwin Backend" cmd /k "cd /d %~dp0backend && venv\Scripts\python.exe main.py"

REM 等待后端启动
timeout /t 3 /nobreak >nul

REM 启动前端
echo [2/2] 启动前端 (Vite :5173)...
start "FabTwin Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo ========================================
echo  启动完成！
echo  前端: http://localhost:5173
echo  后端: http://localhost:8002
echo  API文档: http://localhost:8002/docs
echo ========================================
echo.
echo 关闭对应窗口即可停止服务
pause
