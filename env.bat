@echo off
REM ================================================================
REM FabTwin Environment Configuration
REM 
REM Usage: 
REM   1. Copy this file to your deployment directory
REM   2. Modify the values below for your production Oracle database
REM   3. All bat files (deploy, start, check) read from this file
REM
REM IMPORTANT: 
REM   - Do not use Chinese characters (encoding issues on Windows Server)
REM   - Paths with spaces are OK
REM ================================================================

REM ===== Database Type =====
REM Options: oracle, sqlite
set "DB_TYPE=oracle"

REM ===== Oracle Connection =====
REM Modify these for YOUR production database
set "ORACLE_HOST=10.30.8.119"
set "ORACLE_PORT=1521"
set "ORACLE_SERVICE=APCDB"
set "ORACLE_USER=emuuser"
set "ORACLE_PASSWORD=apcuser"

REM DSN Type: sid (for Oracle 10g/11g) or service_name (for Oracle 12c+)
set "ORACLE_DSN_TYPE=sid"

REM ===== Oracle Client Directory =====
REM Required for Oracle 10g/11g (Thick mode)
REM Point to the Oracle Client root directory (where network\admin exists)
REM Example: C:\app\client\<user>\product\19.0.0\client_1
set "ORACLE_CLIENT_DIR=C:\app\client\c11463\product\19.0.0\client_1"

REM ===== Other Settings =====
set "SIMULATION_ENABLED=False"
set "DB_POLLER_ENABLED=True"