@echo off
REM ================================================================
REM FabTwin Local Database Setup
REM Initialize tables in local Oracle 19c
REM ================================================================

call "%~dp0env_local.bat"

echo ================================================================
echo FabTwin Local DB Setup
echo ================================================================
echo DB: %ORACLE_HOST%:%ORACLE_PORT%/%ORACLE_SERVICE%
echo User: %ORACLE_USER%
echo.

cd /d "%~dp0backend"

echo [1/2] Installing dependencies (if needed)...
if not exist "venv" (
    python -m venv venv
    call venv\Scripts\pip.exe install -r requirements.txt
)

echo [2/2] Initializing database tables...
call venv\Scripts\python.exe -c "
import sys
sys.path.insert(0, '.')
from database import engine, Base, init_db
from models import *
print('Creating tables...')
Base.metadata.create_all(bind=engine)
print('Tables created successfully!')
"

if errorlevel 1 (
    echo [ERROR] Database initialization failed!
    pause
    exit /b 1
)

echo.
echo ================================================================
echo Database initialized successfully!
echo ================================================================
echo.
echo Next: run start_local.bat to start the backend
pause