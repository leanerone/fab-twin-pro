@echo off
title FabTwin DB Init

REM ================================================================
REM FabTwin Database Initialization Script
REM Usage: Execute sql/init_oracle_db.sql to create tables and load base data
REM Prereq: Oracle DB is ready (by DBA team), business user created
REM
REM Usage:
REM   Method 1 (App deployer): Local sqlplus connects to remote Oracle
REM     set ORACLE_HOST=192.168.x.x
REM     set ORACLE_PASSWORD=********
REM     init_db.bat
REM   Method 2 (DBA team): Run on DB server locally
REM     init_db.bat
REM
REM If local has no sqlplus, ask DBA team to run on DB server,
REM or use Python remote execution (see deploy-sop.md section 5.2)
REM ================================================================

setlocal

cd /d %~dp0

REM ---------- Auto detect ORACLE_HOME ----------
if defined ORACLE_HOME (
    echo INFO: Using existing ORACLE_HOME=%ORACLE_HOME%
    goto :run
)

REM Try registry
for /f "tokens=2,*" %%a in ('reg query "HKLM\SOFTWARE\Oracle\KEY_OraDB19Home1" /v ORACLE_HOME 2^>nul ^| findstr ORACLE_HOME') do (
    set "ORACLE_HOME=%%b"
)
for /f "tokens=2,*" %%a in ('reg query "HKLM\SOFTWARE\Oracle\KEY_OraDB18Home1" /v ORACLE_HOME 2^>nul ^| findstr ORACLE_HOME') do (
    set "ORACLE_HOME=%%b"
)
for /f "tokens=2,*" %%a in ('reg query "HKLM\SOFTWARE\Oracle\KEY_OraDB12Home1" /v ORACLE_HOME 2^>nul ^| findstr ORACLE_HOME') do (
    set "ORACLE_HOME=%%b"
)
for /f "tokens=2,*" %%a in ('reg query "HKLM\SOFTWARE\Oracle\KEY_OraClient11Home1" /v ORACLE_HOME 2^>nul ^| findstr ORACLE_HOME') do (
    set "ORACLE_HOME=%%b"
)

if defined ORACLE_HOME (
    echo INFO: Detected ORACLE_HOME=%ORACLE_HOME% from registry
    goto :run
)

REM Try common paths
if exist "C:\oracle\product\19.0.0\dbhome_1\BIN\sqlplus.exe" (
    set "ORACLE_HOME=C:\oracle\product\19.0.0\dbhome_1"
    goto :run
)
if exist "C:\oracle\product\18.0.0\dbhome_1\BIN\sqlplus.exe" (
    set "ORACLE_HOME=C:\oracle\product\18.0.0\dbhome_1"
    goto :run
)
if exist "C:\app\oracle\product\19.0.0\dbhome_1\BIN\sqlplus.exe" (
    set "ORACLE_HOME=C:\app\oracle\product\19.0.0\dbhome_1"
    goto :run
)

REM Try Instant Client
for /f "delims=" %%d in ('dir /b /ad "C:\oracle\instantclient_*" 2^>nul') do (
    if exist "C:\oracle\%%d\sqlplus.exe" (
        set "ORACLE_HOME=C:\oracle\%%d"
        goto :run
    )
)

REM Check PATH for sqlplus
where sqlplus >nul 2>&1
if not errorlevel 1 (
    echo INFO: sqlplus found in PATH
    goto :run_sqlplus
)

echo.
echo ERROR: Cannot find Oracle Home or sqlplus
echo Please set ORACLE_HOME manually, e.g.:
echo   set ORACLE_HOME=C:\oracle\product\19.0.0\dbhome_1
echo Or install Oracle Instant Client and add to PATH
echo.
pause
exit /b 1

:run
set "PATH=%ORACLE_HOME%\BIN;%PATH%"

:run_sqlplus
if not defined ORACLE_SID set "ORACLE_SID=ORCL"

REM Build connection string (from env vars, DBA team provides)
if not defined ORACLE_HOST set "ORACLE_HOST=localhost"
if not defined ORACLE_PORT set "ORACLE_PORT=1521"
if not defined ORACLE_SERVICE set "ORACLE_SERVICE=ORCLPDB"
if not defined ORACLE_USER set "ORACLE_USER=fabtwin"
if not defined ORACLE_PASSWORD set "ORACLE_PASSWORD=fabtwin"

set "CONN_STR=%ORACLE_USER%/%ORACLE_PASSWORD%@%ORACLE_HOST%:%ORACLE_PORT%/%ORACLE_SERVICE%"

echo.
echo ================================================================
echo  FabTwin Database Initialization
echo ================================================================
echo Target DB: %ORACLE_HOST%:%ORACLE_PORT%/%ORACLE_SERVICE%
echo User:      %ORACLE_USER%
echo Script:    sql\init_oracle_db.sql
echo.

if not exist "sql\init_oracle_db.sql" (
    echo ERROR: sql\init_oracle_db.sql not found
    pause
    exit /b 1
)

echo INFO: Connecting as %ORACLE_USER%@%ORACLE_HOST%:%ORACLE_PORT%/%ORACLE_SERVICE%
echo INFO: (Password hidden)
echo.

sqlplus -S "%CONN_STR%" @sql\init_oracle_db.sql > init_db.log 2>&1

if errorlevel 1 (
    echo.
    echo WARNING: sqlplus exited with code %errorlevel%
    echo Please check init_db.log for details
    echo.
    echo Last 20 lines of log:
    powershell -Command "Get-Content init_db.log -Tail 20" 2>nul
    echo.
    pause
    exit /b 1
)

echo.
echo ================================================================
echo  Database initialization completed!
echo ================================================================
echo Log file: init_db.log
echo.
echo Verify:
echo   sqlplus %ORACLE_USER%/***@%ORACLE_HOST%:%ORACLE_PORT%/%ORACLE_SERVICE%
echo   SELECT COUNT(*) FROM user_tables;
echo.
pause
endlocal
