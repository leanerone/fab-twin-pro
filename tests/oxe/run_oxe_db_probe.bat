@echo off
REM ================================================================
REM OXE DB Probe - 采集量产 DB 资料(只读)
REM 用法:
REM   1. 确认 deploy\env.bat 里的 Oracle 配置正确
REM   2. 双击本 bat 或在 CMD 执行 run_oxe_db_probe.bat
REM   3. 把生成的 oxe_db_snapshot_*.json 发给开发同学
REM
REM 本脚本自动调用 ../../deploy/env.bat 读取 Oracle 连接配置
REM ================================================================

chcp 65001 >nul 2>&1
setlocal
title OXE DB Probe

cd /d %~dp0

REM ---------- 加载统一环境配置 ----------
set ENV_BAT=..\..\deploy\env.bat
if not exist "%ENV_BAT%" (
    echo [ERROR] 未找到 env.bat: %ENV_BAT%
    echo 请确认项目目录结构完整, 或手动设置 ORACLE_HOST/PORT/SERVICE/USER/PASSWORD 环境变量
    pause
    exit /b 1
)

call "%ENV_BAT%"
echo [INFO] 已加载 env.bat
echo   ORACLE_HOST=%ORACLE_HOST%
echo   ORACLE_PORT=%ORACLE_PORT%
echo   ORACLE_SERVICE=%ORACLE_SERVICE%
echo   ORACLE_USER=%ORACLE_USER%
echo   ORACLE_DSN_TYPE=%ORACLE_DSN_TYPE%
echo   ORACLE_CLIENT_DIR=%ORACLE_CLIENT_DIR%
echo.

REM ---------- 定位 Python ----------
REM 优先用后端 venv, 没有则用系统 Python
set PYTHON_EXE=python
if exist "..\..\backend\venv\Scripts\python.exe" (
    set PYTHON_EXE=..\..\backend\venv\Scripts\python.exe
    echo [INFO] 使用后端 venv: %PYTHON_EXE%
) else (
    echo [INFO] 使用系统 Python (若未装 oracledb, 请执行: pip install oracledb)
)
echo.

REM ---------- 执行采集 ----------
%PYTHON_EXE% oxe_db_probe.py
if errorlevel 1 (
    echo.
    echo [ERROR] 采集失败, 请查看上方错误信息
    pause
    exit /b 1
)

echo.
echo ================================================================
echo  采集完成! 请把生成的 oxe_db_snapshot_*.json 发给开发同学
echo ================================================================
dir /b oxe_db_snapshot_*.json 2>nul
echo.
pause
endlocal
