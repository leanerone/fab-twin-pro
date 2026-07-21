@echo off
REM ================================================================
REM FabTwin Environment Configuration
REM Modify these values for your production Oracle database
REM All bat files (deploy, start, check) read from this file
REM ================================================================

REM Database type: oracle or sqlite
set "DB_TYPE=oracle"

REM Oracle connection - MODIFY THESE FOR YOUR PRODUCTION DB
set "ORACLE_HOST=10.30.8.119"
set "ORACLE_PORT=1521"
set "ORACLE_SERVICE=APCDB"
set "ORACLE_USER=emuuser"
set "ORACLE_PASSWORD=apcuser"
set "ORACLE_DSN_TYPE=sid"

REM Oracle Client directory (required for 10g/11g thick mode)
set "ORACLE_CLIENT_DIR=C:\app\client\c11463\product\19.0.0\client_1"

REM Other settings
set "SIMULATION_ENABLED=False"
set "DB_POLLER_ENABLED=True"
