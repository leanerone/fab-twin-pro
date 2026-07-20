@echo off
chcp 65001 >nul
title FabTwin 数据库初始化

REM ================================================================
REM FabTwin 数据库初始化脚本
REM 用途：执行 sql/init_oracle_db.sql 创建表结构并导入基础数据
REM 前提：Oracle 数据库已由 DB 组搭建，业务用户已创建
REM
REM 使用方式：
REM   方式1（应用部署方）：本机有 sqlplus，通过远程连接 DB 组的 Oracle 执行
REM     set ORACLE_HOST=192.168.x.x
REM     set ORACLE_PASSWORD=********
REM     init_db.bat
REM   方式2（DB 组）：在 DB 服务器本地直接执行
REM     init_db.bat
REM
REM 如本机无 sqlplus，建议由 DB 组在 DB 服务器执行
REM 或使用 Python 远程执行（见 deploy-sop.md 5.2）
REM ================================================================

setlocal

cd /d %~dp0

REM ---------- 自动检测 ORACLE_HOME ----------
if defined ORACLE_HOME (
    echo INFO: 使用已有 ORACLE_HOME=%ORACLE_HOME%
    goto :run
)

REM 尝试从注册表读取 Oracle Home
for /f "tokens=2,*" %%a in ('reg query "HKLM\SOFTWARE\Oracle\KEY_OraDB19Home1" /v ORACLE_HOME 2^>nul ^| findstr ORACLE_HOME') do (
    set "ORACLE_HOME=%%b"
)

if defined ORACLE_HOME (
    echo INFO: 从注册表检测到 ORACLE_HOME=%ORACLE_HOME%
    goto :run
)

REM 尝试常见安装路径
if exist "C:\oracle\product\19.0.0\dbhome_1\BIN\sqlplus.exe" (
    set "ORACLE_HOME=C:\oracle\product\19.0.0\dbhome_1"
    echo INFO: 使用常见路径 ORACLE_HOME=%ORACLE_HOME%
    goto :run
)

if exist "C:\app\oracle\product\19.0.0\dbhome_1\BIN\sqlplus.exe" (
    set "ORACLE_HOME=C:\app\oracle\product\19.0.0\dbhome_1"
    echo INFO: 使用常见路径 ORACLE_HOME=%ORACLE_HOME%
    goto :run
)

REM 尝试 Instant Client
for /f "delims=" %%d in ('dir /b /ad "C:\oracle\instantclient_*" 2^>nul') do (
    if exist "C:\oracle\%%d\sqlplus.exe" (
        set "ORACLE_HOME=C:\oracle\%%d"
        echo INFO: 使用 Instant Client ORACLE_HOME=%ORACLE_HOME%
        goto :run
    )
)

REM 检查 PATH 中是否有 sqlplus
where sqlplus >nul 2>&1
if not errorlevel 1 (
    echo INFO: sqlplus 已在 PATH 中
    goto :run_sqlplus
)

echo ERROR: 未找到 Oracle Home 或 sqlplus
echo 请手动设置 ORACLE_HOME 环境变量，例如:
echo   set ORACLE_HOME=C:\oracle\product\19.0.0\dbhome_1
echo 或安装 Oracle Instant Client 并加入 PATH
pause
exit /b 1

:run
set "PATH=%ORACLE_HOME%\BIN;%PATH%"

:run_sqlplus
if not defined ORACLE_SID set "ORACLE_SID=ORCL"

REM 使用环境变量构建连接串（DB 组提供）
if not defined ORACLE_HOST set "ORACLE_HOST=localhost"
if not defined ORACLE_PORT set "ORACLE_PORT=1521"
if not defined ORACLE_SERVICE set "ORACLE_SERVICE=ORCLPDB"
if not defined ORACLE_USER set "ORACLE_USER=fabtwin"
if not defined ORACLE_PASSWORD set "ORACLE_PASSWORD=fabtwin"

set "CONN_STR=%ORACLE_USER%/%ORACLE_PASSWORD%@%ORACLE_HOST%:%ORACLE_PORT%/%ORACLE_SERVICE%"

echo.
echo ================================================================
echo  开始初始化数据库...
echo ================================================================
echo 目标数据库: %ORACLE_HOST%:%ORACLE_PORT%/%ORACLE_SERVICE%
echo 业务用户:   %ORACLE_USER%
echo 执行脚本:   sql\init_oracle_db.sql
echo.

if not exist "sql\init_oracle_db.sql" (
    echo ERROR: 未找到 sql\init_oracle_db.sql
    pause
    exit /b 1
)

echo INFO: 连接串: %ORACLE_USER%/******@%ORACLE_HOST%:%ORACLE_PORT%/%ORACLE_SERVICE%
sqlplus -S "%CONN_STR%" @sql\init_oracle_db.sql > init_db.log 2>&1

if errorlevel 1 (
    echo WARNING: sqlplus 退出码 %errorlevel%，请查看 init_db.log
    echo.
    type init_db.log | more
    pause
    exit /b 1
)

echo.
echo ================================================================
echo  数据库初始化完成！
echo ================================================================
echo 日志文件: init_db.log
echo.
echo 验证:
echo   sqlplus %ORACLE_USER%/******@%ORACLE_HOST%:%ORACLE_PORT%/%ORACLE_SERVICE%
echo   SELECT COUNT(*) FROM user_tables;
echo.
pause
endlocal
