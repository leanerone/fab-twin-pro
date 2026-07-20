@echo off
chcp 65001 >nul
title FabTwin 创建 Oracle 用户

REM ================================================================
REM FabTwin Oracle 用户创建脚本
REM 用途：创建 fabtwin 业务用户、表空间、授权
REM 前提：Oracle 服务已启动，执行者有 sysdba 权限
REM ================================================================

setlocal
cd /d %~dp0

REM ---------- 自动检测 ORACLE_HOME ----------
if not defined ORACLE_HOME (
    for /f "tokens=2,*" %%a in ('reg query "HKLM\SOFTWARE\Oracle\KEY_OraDB19Home1" /v ORACLE_HOME 2^>nul ^| findstr ORACLE_HOME') do (
        set "ORACLE_HOME=%%b"
    )
)

if not defined ORACLE_HOME (
    if exist "C:\oracle\product\19.0.0\dbhome_1\BIN\sqlplus.exe" (
        set "ORACLE_HOME=C:\oracle\product\19.0.0\dbhome_1"
    )
)

if not defined ORACLE_HOME (
    if exist "C:\app\oracle\product\19.0.0\dbhome_1\BIN\sqlplus.exe" (
        set "ORACLE_HOME=C:\app\oracle\product\19.0.0\dbhome_1"
    )
)

if defined ORACLE_HOME (
    set "PATH=%ORACLE_HOME%\BIN;%PATH%"
    echo INFO: ORACLE_HOME=%ORACLE_HOME%
)

set "ORACLE_SID=ORCL"

echo.
echo ================================================================
echo  创建 fabtwin 用户（需 sysdba 权限）
echo ================================================================
echo.

if not exist "create_user.sql" (
    echo ERROR: 未找到 create_user.sql
    pause
    exit /b 1
)

sqlplus /nolog @create_user.sql

if errorlevel 1 (
    echo WARNING: sqlplus 退出码 %errorlevel%
    pause
    exit /b 1
)

echo.
echo 用户创建完成！接下来请运行 init_db.bat 初始化表结构
echo.
pause
endlocal
