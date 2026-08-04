@echo off
REM FabTwin Environment Configuration
REM Modify these values for your production Oracle database
REM IMPORTANT: Do NOT use Chinese characters in this file

REM Database Type: oracle (only oracle is supported)
set DB_TYPE=oracle

REM Oracle Connection
set ORACLE_HOST=10.30.8.119
set ORACLE_PORT=1521
set ORACLE_SERVICE=APCDB
set ORACLE_USER=emuuser
set ORACLE_PASSWORD=apcuser

REM DSN Type: sid (Oracle 10g/11g) or service_name (Oracle 12c+)
set ORACLE_DSN_TYPE=sid

REM Oracle Client Directory (required for Thick mode)
set ORACLE_CLIENT_DIR=C:\app\client\c11463\product\19.0.0\client_1

REM Other Settings
set SIMULATION_ENABLED=False
set DB_POLLER_ENABLED=True
