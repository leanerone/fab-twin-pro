@echo off
REM ================================================================
REM FabTwin LOCAL Environment Configuration
REM Local Oracle 19c on C:\oracle
REM ================================================================

set "DB_TYPE=oracle"
set "ORACLE_HOST=localhost"
set "ORACLE_PORT=1521"
set "ORACLE_SERVICE=ORCLPDB"
set "ORACLE_USER=fabtwin"
set "ORACLE_PASSWORD=fabtwin"
set "ORACLE_DSN_TYPE=service_name"
set "ORACLE_CLIENT_DIR=C:\oracle\WINDOWS.X64_193000_db_home"

set "SIMULATION_ENABLED=False"
set "DB_POLLER_ENABLED=True"