@echo off
setlocal enabledelayedexpansion

title FabTwin Oracle Diagnostic Tool

REM ================================================================
REM FabTwin Oracle Client Self-Diagnostic and Repair Tool
REM Usage: Run on production server to check/repair Oracle Client
REM Output: oracle_check_report.txt
REM ================================================================

set "BASE_DIR=%~dp0"
set "BASE_DIR=%BASE_DIR:~0,-1%"
set "BACKEND_DIR=%BASE_DIR%\backend"
set "REPORT=%BASE_DIR%\oracle_check_report.txt"
set "PY_EXE=%BACKEND_DIR%\venv\Scripts\python.exe"

set "FIXED=0"
set "ERRORS=0"

echo ===============================================================
echo  FabTwin Oracle Client Diagnostic Tool
echo ===============================================================
echo.
echo This tool checks Oracle Client installation for python-oracledb.
echo Report will be saved to: %REPORT%
echo.

REM Clear report
echo FabTwin Oracle Diagnostic Report > "%REPORT%"
echo Generated: %date% %time% >> "%REPORT%"
echo ====================================================== >> "%REPORT%"
echo. >> "%REPORT%"

REM ---------- Check 1: Python exists ----------
echo [1/8] Checking Python venv...
echo [1/8] Checking Python venv... >> "%REPORT%"
if not exist "%PY_EXE%" (
    echo   ERROR: Python not found at %PY_EXE%
    echo   ERROR: Python not found at %PY_EXE% >> "%REPORT%"
    echo   Please run deploy.bat first to create venv.
    set /a ERRORS+=1
    pause
    exit /b 1
)
echo   OK: %PY_EXE%
echo   OK: %PY_EXE% >> "%REPORT%"

REM ---------- Check 2: Python bitness ----------
echo.
echo [2/8] Checking Python architecture...
echo [2/8] Checking Python architecture... >> "%REPORT%"
for /f "usebackq delims=" %%a in (`"%PY_EXE%" -c "import struct; print(struct.calcsize('P')*8)"`) do set "PY_BITS=%%a"
echo   Python is %PY_BITS%-bit
echo   Python is %PY_BITS%-bit >> "%REPORT%"
if not "%PY_BITS%"=="64" (
    echo   ERROR: Python must be 64-bit to match 64-bit Oracle Client.
    echo   ERROR: Python must be 64-bit to match 64-bit Oracle Client. >> "%REPORT%"
    set /a ERRORS+=1
) else (
    echo   OK: Python is 64-bit
echo   OK: Python is 64-bit >> "%REPORT%"
)

REM ---------- Check 3: Find Oracle Client ----------
echo.
echo [3/8] Searching for Oracle Client (oci.dll)...
echo [3/8] Searching for Oracle Client (oci.dll)... >> "%REPORT%"

set "CLIENT_DIR="
set "CLIENT_FOUND=0"

REM Check env var first
if defined ORACLE_CLIENT_DIR (
    if exist "%ORACLE_CLIENT_DIR%\bin\oci.dll" (
        echo   Found from ORACLE_CLIENT_DIR: %ORACLE_CLIENT_DIR%
        echo   Found from ORACLE_CLIENT_DIR: %ORACLE_CLIENT_DIR% >> "%REPORT%"
        set "CLIENT_DIR=%ORACLE_CLIENT_DIR%"
        set "CLIENT_FOUND=1"
    ) else (
        echo   WARNING: ORACLE_CLIENT_DIR is set but oci.dll not found
        echo   WARNING: ORACLE_CLIENT_DIR=%ORACLE_CLIENT_DIR% but no oci.dll >> "%REPORT%"
    )
)

REM Search common paths
if "%CLIENT_FOUND%"=="0" (
    for %%p in (
        "C:\app\client\*\product\19.*\client_1"
        "C:\oracle\product\19.*\client_1"
        "C:\oracle\product\19.*\dbhome_1"
        "C:\oracle\instantclient_19_*"
        "C:\app\oracle\product\19.*\client_1"
        "N:\WINDOWS.X64_193000_db_home"
    ) do (
        if exist "%%~p\bin\oci.dll" (
            echo   Found Oracle Client: %%~p
            echo   Found Oracle Client: %%~p >> "%REPORT%"
            set "CLIENT_DIR=%%~p"
            set "CLIENT_FOUND=1"
            goto :found_client
        )
    )
)
:found_client

if "%CLIENT_FOUND%"=="0" (
    echo   ERROR: Oracle Client (oci.dll) not found in common paths.
    echo   ERROR: Oracle Client (oci.dll) not found. >> "%REPORT%"
    echo   Please install Oracle Instant Client 19c x64 and set ORACLE_CLIENT_DIR.
    set /a ERRORS+=1
    goto :summary
)

echo   CLIENT_DIR=%CLIENT_DIR%
echo   CLIENT_DIR=%CLIENT_DIR% >> "%REPORT%"

REM ---------- Check 4: Check PATH ----------
echo.
echo [4/8] Checking PATH contains Oracle bin...
echo [4/8] Checking PATH contains Oracle bin... >> "%REPORT%"
set "BIN_DIR=%CLIENT_DIR%\bin"
echo "%PATH%" | find /i "%BIN_DIR%" >nul
if errorlevel 1 (
    echo   WARNING: PATH does not contain %BIN_DIR%
    echo   WARNING: PATH does not contain %BIN_DIR% >> "%REPORT%"
    echo   Attempting to add to system PATH...
    echo   Attempting to add to system PATH... >> "%REPORT%"
    setx PATH "%PATH%;%BIN_DIR%" >nul 2>&1
    if errorlevel 1 (
        echo   WARNING: Failed to set PATH automatically (may need admin)
        echo   WARNING: Failed to set PATH automatically >> "%REPORT%"
    ) else (
        echo   FIXED: Added %BIN_DIR% to system PATH
        echo   FIXED: Added %BIN_DIR% to system PATH >> "%REPORT%"
        set /a FIXED+=1
    )
) else (
    echo   OK: PATH contains Oracle bin
    echo   OK: PATH contains Oracle bin >> "%REPORT%"
)

REM ---------- Check 5: Check ORACLE_CLIENT_DIR env var ----------
echo.
echo [5/8] Checking ORACLE_CLIENT_DIR env var...
echo [5/8] Checking ORACLE_CLIENT_DIR env var... >> "%REPORT%"
if "%ORACLE_CLIENT_DIR%"=="%CLIENT_DIR%" (
    echo   OK: ORACLE_CLIENT_DIR is set correctly
    echo   OK: ORACLE_CLIENT_DIR=%ORACLE_CLIENT_DIR% >> "%REPORT%"
) else (
    echo   Setting ORACLE_CLIENT_DIR=%CLIENT_DIR%
    echo   Setting ORACLE_CLIENT_DIR=%CLIENT_DIR% >> "%REPORT%"
    setx ORACLE_CLIENT_DIR "%CLIENT_DIR%" >nul 2>&1
    if errorlevel 1 (
        echo   WARNING: Failed to set ORACLE_CLIENT_DIR (may need admin)
        echo   WARNING: Failed to set ORACLE_CLIENT_DIR >> "%REPORT%"
    ) else (
        echo   FIXED: Set ORACLE_CLIENT_DIR=%CLIENT_DIR%
        echo   FIXED: Set ORACLE_CLIENT_DIR=%CLIENT_DIR% >> "%REPORT%"
        set /a FIXED+=1
    )
)

REM ---------- Check 6: Check VC++ Redistributables ----------
echo.
echo [5/8] Checking Visual C++ Redistributables...
echo [5/8] Checking Visual C++ Redistributables... >> "%REPORT%"

set "VCPKG_DLLS=MSVCR120.dll MSVCP120.dll VCRUNTIME140.dll MSVCP140.dll VCRUNTIME140_1.dll"
set "MISSING_DLLS="
for %%d in (%VCPKG_DLLS%) do (
    if not exist "%BIN_DIR%\%%d" (
        if not exist "C:\Windows\System32\%%d" (
            set "MISSING_DLLS=!MISSING_DLLS! %%d"
        )
    )
)

if "!MISSING_DLLS!"=="" (
    echo   OK: Required VC++ runtime DLLs found
    echo   OK: Required VC++ runtime DLLs found >> "%REPORT%"
) else (
    echo   WARNING: Missing VC++ DLLs:%MISSING_DLLS%
    echo   WARNING: Missing VC++ DLLs:%MISSING_DLLS% >> "%REPORT%"
    echo   Please install:
    echo   - Microsoft Visual C++ 2013 Redistributable (x64)
    echo   - Microsoft Visual C++ 2015-2022 Redistributable (x64)
    echo   Download: https://aka.ms/vs/17/release/vc_redist.x64.exe
    set /a ERRORS+=1
)

REM ---------- Check 7: Test Thick mode in Python ----------
echo.
echo [7/8] Testing python-oracledb Thick mode...
echo [7/8] Testing python-oracledb Thick mode... >> "%REPORT%"

(
echo import oracledb, sys
echo try:
echo     oracledb.init_oracle_client^(lib_dir=r'%CLIENT_DIR%'^)
echo     print^('THICK_OK', oracledb.clientversion^(^)^)
echo except Exception as e:
echo     print^('THICK_FAILED', str^(e^)^)
echo     sys.exit^(1^)
) > "%BASE_DIR%\_check_thick.py"

for /f "usebackq tokens=1,* delims= " %%a in (`"%PY_EXE%" "%BASE_DIR%\_check_thick.py"`) do (
    set "THICK_STATUS=%%a"
    set "THICK_DETAIL=%%b"
)

if "%THICK_STATUS%"=="THICK_OK" (
    echo   OK: Thick mode loaded, client version: %THICK_DETAIL%
    echo   OK: Thick mode loaded, client version: %THICK_DETAIL% >> "%REPORT%"
) else (
    echo   ERROR: Thick mode failed: %THICK_DETAIL%
    echo   ERROR: Thick mode failed: %THICK_DETAIL% >> "%REPORT%"
    echo   Common fix: Install VC++ Redistributables and restart cmd.
    set /a ERRORS+=1
)

del "%BASE_DIR%\_check_thick.py" >nul 2>&1

REM ---------- Check 8: Test DB connection ----------
echo.
echo [8/8] Testing Oracle connection...
echo [8/8] Testing Oracle connection... >> "%REPORT%"

REM Read Oracle config from deploy.bat if present
set "TEST_HOST="
set "TEST_PORT=1521"
set "TEST_SERVICE="
set "TEST_USER="
set "TEST_PASSWORD="
set "TEST_DSN_TYPE=sid"

if exist "%BASE_DIR%\deploy.bat" (
    for /f "usebackq tokens=*" %%l in ("%BASE_DIR%\deploy.bat") do (
        echo %%l | findstr /i /c:"set \"ORACLE_HOST=" >nul && for /f "tokens=2 delims==" %%v in ("%%l") do set "TEST_HOST=%%v"
        echo %%l | findstr /i /c:"set \"ORACLE_PORT=" >nul && for /f "tokens=2 delims==" %%v in ("%%l") do set "TEST_PORT=%%v"
        echo %%l | findstr /i /c:"set \"ORACLE_SERVICE=" >nul && for /f "tokens=2 delims==" %%v in ("%%l") do set "TEST_SERVICE=%%v"
        echo %%l | findstr /i /c:"set \"ORACLE_USER=" >nul && for /f "tokens=2 delims==" %%v in ("%%l") do set "TEST_USER=%%v"
        echo %%l | findstr /i /c:"set \"ORACLE_PASSWORD=" >nul && for /f "tokens=2 delims==" %%v in ("%%l") do set "TEST_PASSWORD=%%v"
        echo %%l | findstr /i /c:"set \"ORACLE_DSN_TYPE=" >nul && for /f "tokens=2 delims==" %%v in ("%%l") do set "TEST_DSN_TYPE=%%v"
    )
)

REM Trim trailing quote
set "TEST_HOST=%TEST_HOST:~0,-1%"
set "TEST_PORT=%TEST_PORT:~0,-1%"
set "TEST_SERVICE=%TEST_SERVICE:~0,-1%"
set "TEST_USER=%TEST_USER:~0,-1%"
set "TEST_PASSWORD=%TEST_PASSWORD:~0,-1%"
set "TEST_DSN_TYPE=%TEST_DSN_TYPE:~0,-1%"

if "%TEST_HOST%"=="" (
    echo   SKIP: Oracle host not configured in deploy.bat
    echo   SKIP: Oracle host not configured in deploy.bat >> "%REPORT%"
    echo   Uncomment and set ORACLE_* vars in deploy.bat first.
) else (
    echo   Config: %TEST_USER%/%TEST_PASSWORD%@%TEST_HOST%:%TEST_PORT%:%TEST_SERVICE% ^(DSN_TYPE=%TEST_DSN_TYPE%^)
    echo   Config: %TEST_USER% @ %TEST_HOST%:%TEST_PORT% ^(%TEST_DSN_TYPE%=%TEST_SERVICE%^) >> "%REPORT%"
    (
    echo import oracledb, sys
echo try:
echo     oracledb.init_oracle_client^(lib_dir=r'%CLIENT_DIR%'^)
echo     dsn = oracledb.makedsn^('%TEST_HOST%', %TEST_PORT%, sid='%TEST_SERVICE%'^) if '%TEST_DSN_TYPE%' == 'sid' else oracledb.makedsn^('%TEST_HOST%', %TEST_PORT%, service_name='%TEST_SERVICE%'^)
echo     conn = oracledb.connect^(user='%TEST_USER%', password='%TEST_PASSWORD%', dsn=dsn^)
echo     cur = conn.cursor^(^)
echo     cur.execute^('SELECT * FROM v$version'^)
echo     print^('CONNECT_OK', cur.fetchone^(^)[0]^)
echo     conn.close^(^)
echo except Exception as e:
echo     print^('CONNECT_FAILED', str^(e^)^)
echo     sys.exit^(1^)
    ) > "%BASE_DIR%\_check_conn.py"

    for /f "usebackq tokens=1,* delims= " %%a in (`"%PY_EXE%" "%BASE_DIR%\_check_conn.py"`) do (
        set "CONN_STATUS=%%a"
        set "CONN_DETAIL=%%b"
    )

    if "%CONN_STATUS%"=="CONNECT_OK" (
        echo   OK: Connected to Oracle: %CONN_DETAIL%
        echo   OK: Connected to Oracle: %CONN_DETAIL% >> "%REPORT%"
    ) else (
        echo   ERROR: Connection failed: %CONN_DETAIL%
        echo   ERROR: Connection failed: %CONN_DETAIL% >> "%REPORT%"
        set /a ERRORS+=1
    )

    del "%BASE_DIR%\_check_conn.py" >nul 2>&1
)

:summary
echo.
echo ===============================================================
echo  Summary
echo ===============================================================
if %ERRORS%==0 (
    echo  Result: ALL CHECKS PASSED ^(%FIXED% auto-fixes applied^)
    echo  Result: ALL CHECKS PASSED ^(%FIXED% auto-fixes applied^) >> "%REPORT%"
) else (
    echo  Result: %ERRORS% error^(s^) found, %FIXED% auto-fix^(es^) applied
    echo  Result: %ERRORS% error^(s^) found, %FIXED% auto-fix^(es^) applied >> "%REPORT%"
)
echo.
echo  Full report: %REPORT%
echo.
echo  IMPORTANT: If any auto-fixes were applied, close this window and
echo  open a NEW command prompt, then run deploy.bat again.
echo.
echo ===============================================================
pause
endlocal
