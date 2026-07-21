@echo off
setlocal enabledelayedexpansion

title FabTwin Oracle DB Connection Test

REM ================================================================
REM FabTwin Oracle Database Connection Test Tool
REM Tests DB connection via: sqlplus, python-oracledb Thick, python-oracledb Thin
REM Modify DB_* vars below if needed, then run this bat
REM ================================================================

REM ---------- Default DB config from your production environment ----------
REM Change these values if your DB config is different
set "DB_HOST=10.30.8.119"
set "DB_PORT=1521"
set "DB_SID=APCDB"
set "DB_USER=emuuser"
set "DB_PASSWORD=apcuser"
set "DB_DSN_TYPE=sid"

REM Oracle Client directory (Thick mode only, leave empty to auto-detect)
set "ORACLE_CLIENT_DIR="

set "BASE_DIR=%~dp0"
set "BASE_DIR=%BASE_DIR:~0,-1%"
set "BACKEND_DIR=%BASE_DIR%\backend"
set "PY_EXE=%BACKEND_DIR%\venv\Scripts\python.exe"
set "REPORT=%BASE_DIR%\db_connection_report.txt"

echo ===============================================================
echo  FabTwin Oracle DB Connection Test
echo ===============================================================
echo.
echo  Target DB: %DB_USER%/%DB_PASSWORD%@%DB_HOST%:%DB_PORT%:%DB_SID%
echo  DSN Type:  %DB_DSN_TYPE%
echo.

REM Clear report
echo FabTwin Oracle DB Connection Test Report > "%REPORT%"
echo Generated: %date% %time% >> "%REPORT%"
echo Target DB: %DB_USER% @ %DB_HOST%:%DB_PORT% ^(%DB_DSN_TYPE%=%DB_SID%^) >> "%REPORT%"
echo ====================================================== >> "%REPORT%"
echo. >> "%REPORT%"

REM ---------- Test 1: sqlplus ----------
echo [1/4] Testing with sqlplus...
echo [1/4] Testing with sqlplus... >> "%REPORT%"
where sqlplus >nul 2>&1
if errorlevel 1 (
    echo   SKIP: sqlplus not found in PATH
echo   SKIP: sqlplus not found in PATH >> "%REPORT%"
) else (
    echo   Running: sqlplus -S %DB_USER%/%DB_PASSWORD%@%DB_HOST%:%DB_PORT%/%DB_SID%
    echo   Running: sqlplus %DB_USER%/%DB_PASSWORD%@%DB_HOST%:%DB_PORT%/%DB_SID% >> "%REPORT%"
    (
    echo SELECT * FROM v$version;
    echo EXIT;
    ) > "%BASE_DIR%\_test_sqlplus.sql"
    sqlplus -S %DB_USER%/%DB_PASSWORD%@%DB_HOST%:%DB_PORT%/%DB_SID% @"%BASE_DIR%\_test_sqlplus.sql" > "%BASE_DIR%\_test_sqlplus.log" 2>&1
    if errorlevel 1 (
        echo   FAILED: sqlplus connection failed
echo   FAILED: sqlplus connection failed >> "%REPORT%"
        type "%BASE_DIR%\_test_sqlplus.log" >> "%REPORT%"
    ) else (
        echo   OK: sqlplus connected successfully
echo   OK: sqlplus connected successfully >> "%REPORT%"
        type "%BASE_DIR%\_test_sqlplus.log" >> "%REPORT%"
    )
    del "%BASE_DIR%\_test_sqlplus.sql" >nul 2>&1
    del "%BASE_DIR%\_test_sqlplus.log" >nul 2>&1
)

REM ---------- Test 2: python-oracledb Thin mode ----------
echo.
echo [2/4] Testing with python-oracledb Thin mode...
echo [2/4] Testing with python-oracledb Thin mode... >> "%REPORT%"
if not exist "%PY_EXE%" (
    echo   SKIP: Python venv not found at %PY_EXE%
echo   SKIP: Python venv not found >> "%REPORT%"
) else (
    (
    echo import oracledb, sys
echo try:
echo     dsn = oracledb.makedsn^('%DB_HOST%', %DB_PORT%, sid='%DB_SID%'^) if '%DB_DSN_TYPE%' == 'sid' else oracledb.makedsn^('%DB_HOST%', %DB_PORT%, service_name='%DB_SID%'^)
echo     conn = oracledb.connect^(user='%DB_USER%', password='%DB_PASSWORD%', dsn=dsn^)
echo     cur = conn.cursor^(^)
echo     cur.execute^('SELECT * FROM v$version'^)
echo     print^('THIN_OK', cur.fetchone^(^)[0]^)
echo     conn.close^(^)
echo except Exception as e:
echo     print^('THIN_FAILED', str^(e^)^)
echo     sys.exit^(1^)
    ) > "%BASE_DIR%\_test_thin.py"

    for /f "tokens=1,* delims= " %%a in ('"%PY_EXE%" "%BASE_DIR%\_test_thin.py"') do (
        set "THIN_STATUS=%%a"
        set "THIN_DETAIL=%%b"
    )

    if "%THIN_STATUS%"=="THIN_OK" (
        echo   OK: Thin mode connected: %THIN_DETAIL%
echo   OK: Thin mode connected: %THIN_DETAIL% >> "%REPORT%"
    ) else (
        echo   FAILED: Thin mode: %THIN_DETAIL%
echo   FAILED: Thin mode: %THIN_DETAIL% >> "%REPORT%"
    )

    del "%BASE_DIR%\_test_thin.py" >nul 2>&1
)

REM ---------- Test 3: python-oracledb Thick mode ----------
echo.
echo [3/4] Testing with python-oracledb Thick mode...
echo [3/4] Testing with python-oracledb Thick mode... >> "%REPORT%"
if not exist "%PY_EXE%" (
    echo   SKIP: Python venv not found
echo   SKIP: Python venv not found >> "%REPORT%"
    goto :summary
)

REM Auto-detect Oracle Client if not set
if "%ORACLE_CLIENT_DIR%"=="" (
    if defined ORACLE_CLIENT_DIR (
        set "ORACLE_CLIENT_DIR=%ORACLE_CLIENT_DIR%"
    ) else (
        for %%p in (
            "C:\app\client\*\product\19.*\client_1"
            "C:\oracle\product\19.*\client_1"
            "C:\oracle\product\19.*\dbhome_1"
            "C:\oracle\instantclient_19_*"
            "C:\app\oracle\product\19.*\client_1"
        ) do (
            if exist "%%~p\bin\oci.dll" (
                set "ORACLE_CLIENT_DIR=%%~p"
                goto :thick_found
            )
        )
    )
)
:thick_found

if "%ORACLE_CLIENT_DIR%"=="" (
    echo   SKIP: Oracle Client not found, cannot test Thick mode
echo   SKIP: Oracle Client not found >> "%REPORT%"
    goto :summary
)

echo   Using Oracle Client: %ORACLE_CLIENT_DIR%
echo   Using Oracle Client: %ORACLE_CLIENT_DIR% >> "%REPORT%"

(
echo import oracledb, sys
echo try:
echo     oracledb.init_oracle_client^(lib_dir=r'%ORACLE_CLIENT_DIR%'^)
echo     dsn = oracledb.makedsn^('%DB_HOST%', %DB_PORT%, sid='%DB_SID%'^) if '%DB_DSN_TYPE%' == 'sid' else oracledb.makedsn^('%DB_HOST%', %DB_PORT%, service_name='%DB_SID%'^)
echo     conn = oracledb.connect^(user='%DB_USER%', password='%DB_PASSWORD%', dsn=dsn^)
echo     cur = conn.cursor^(^)
echo     cur.execute^('SELECT * FROM v$version'^)
echo     print^('THICK_OK', cur.fetchone^(^)[0]^)
echo     conn.close^(^)
echo except Exception as e:
echo     print^('THICK_FAILED', str^(e^)^)
echo     sys.exit^(1^)
) > "%BASE_DIR%\_test_thick.py"

for /f "tokens=1,* delims= " %%a in ('"%PY_EXE%" "%BASE_DIR%\_test_thick.py"') do (
    set "THICK_STATUS=%%a"
    set "THICK_DETAIL=%%b"
)

if "%THICK_STATUS%"=="THICK_OK" (
    echo   OK: Thick mode connected: %THICK_DETAIL%
echo   OK: Thick mode connected: %THICK_DETAIL% >> "%REPORT%"
) else (
    echo   FAILED: Thick mode: %THICK_DETAIL%
echo   FAILED: Thick mode: %THICK_DETAIL% >> "%REPORT%"
)

del "%BASE_DIR%\_test_thick.py" >nul 2>&1

REM ---------- Test 4: Backend config test ----------
echo.
echo [4/4] Testing backend config.py connection...
echo [4/4] Testing backend config.py connection... >> "%REPORT%"
if not exist "%PY_EXE%" (
    echo   SKIP: Python venv not found
echo   SKIP: Python venv not found >> "%REPORT%"
) else (
    (
echo import os, sys
echo os.environ['DB_TYPE'] = 'oracle'
echo os.environ['ORACLE_HOST'] = '%DB_HOST%'
echo os.environ['ORACLE_PORT'] = '%DB_PORT%'
echo os.environ['ORACLE_USER'] = '%DB_USER%'
echo os.environ['ORACLE_PASSWORD'] = '%DB_PASSWORD%'
echo os.environ['ORACLE_SERVICE'] = '%DB_SID%'
echo os.environ['ORACLE_DSN_TYPE'] = '%DB_DSN_TYPE%'
echo if '%ORACLE_CLIENT_DIR%' != '': os.environ['ORACLE_CLIENT_DIR'] = '%ORACLE_CLIENT_DIR%'
echo sys.path.insert^(0, r'%BACKEND_DIR%'^)
echo try:
echo     from database import engine
echo     conn = engine.connect^(^)
echo     result = conn.execute^(__import__^('sqlalchemy'^).text^('SELECT * FROM v$version'^)^)
echo     print^('BACKEND_OK', result.scalar^(^)^)
echo     conn.close^(^)
echo except Exception as e:
echo     print^('BACKEND_FAILED', str^(e^)^)
echo     sys.exit^(1^)
    ) > "%BASE_DIR%\_test_backend.py"

    for /f "tokens=1,* delims= " %%a in ('"%PY_EXE%" "%BASE_DIR%\_test_backend.py"') do (
        set "BACK_STATUS=%%a"
        set "BACK_DETAIL=%%b"
    )

    if "%BACK_STATUS%"=="BACKEND_OK" (
        echo   OK: Backend config connected: %BACK_DETAIL%
echo   OK: Backend config connected: %BACK_DETAIL% >> "%REPORT%"
    ) else (
        echo   FAILED: Backend config: %BACK_DETAIL%
echo   FAILED: Backend config: %BACK_DETAIL% >> "%REPORT%"
    )

    del "%BASE_DIR%\_test_backend.py" >nul 2>&1
)

:summary
echo.
echo ===============================================================
echo  Test Complete
echo ===============================================================
echo  Full report: %REPORT%
echo.
echo  If Thick mode fails but sqlplus works:
echo    - Install Visual C++ Redistributables
echo    - Check ORACLE_CLIENT_DIR points to correct path
echo.
echo  If both Thick and Thin fail:
echo    - Check DB_HOST / DB_SID / DB_USER / DB_PASSWORD
echo    - Check firewall / listener status
echo.
echo  If Backend config fails but Thick mode works:
echo    - Check deploy.bat passes all Oracle env vars correctly
echo.
echo ===============================================================
pause
endlocal
