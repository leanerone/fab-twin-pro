@echo off
title FabTwin Create Oracle User

REM ================================================================
REM FabTwin Oracle User Creation Script
REM Usage: Create fabtwin business user, tablespace, grants
REM Prereq: Oracle DB is running, executor has sysdba privilege
REM
REM Note: Usually this is done by DBA team on the Oracle server.
REM       App deployer can send create_user.sql to DBA team to run.
REM ================================================================

setlocal
cd /d %~dp0

REM ---------- Auto detect ORACLE_HOME ----------
if not defined ORACLE_HOME (
    for /f "tokens=2,*" %%a in ('reg query "HKLM\SOFTWARE\Oracle\KEY_OraDB19Home1" /v ORACLE_HOME 2^>nul ^| findstr ORACLE_HOME') do (
        set "ORACLE_HOME=%%b"
    )
    for /f "tokens=2,*" %%a in ('reg query "HKLM\SOFTWARE\Oracle\KEY_OraDB18Home1" /v ORACLE_HOME 2^>nul ^| findstr ORACLE_HOME') do (
        set "ORACLE_HOME=%%b"
    )
    for /f "tokens=2,*" %%a in ('reg query "HKLM\SOFTWARE\Oracle\KEY_OraDB12Home1" /v ORACLE_HOME 2^>nul ^| findstr ORACLE_HOME') do (
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
echo  Creating fabtwin user (requires sysdba privilege)
echo ================================================================
echo.

if not exist "create_user.sql" (
    echo ERROR: create_user.sql not found
    pause
    exit /b 1
)

sqlplus /nolog @create_user.sql

if errorlevel 1 (
    echo WARNING: sqlplus exited with code %errorlevel%
    pause
    exit /b 1
)

echo.
echo User creation done. Next: run init_db.bat to initialize schema
echo.
pause
endlocal
