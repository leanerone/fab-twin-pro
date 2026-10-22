@echo off
REM FabTwin Local Dev Environment (Oracle XE 21c on localhost)
REM IMPORTANT: Do NOT use Chinese characters in this file

set DB_TYPE=oracle

set ORACLE_HOST=localhost
set ORACLE_PORT=1521
set ORACLE_SERVICE=XEPDB1
set ORACLE_USER=fabtwin
set ORACLE_PASSWORD=fabtwin

REM DSN Type: service_name (Oracle 12c+ PDB)
set ORACLE_DSN_TYPE=service_name

REM Oracle Client Directory (empty = python-oracledb Thin mode)
set ORACLE_CLIENT_DIR=

set SIMULATION_ENABLED=False
set DB_POLLER_ENABLED=True

REM T7: Garnet cache (redis-py RESP compatible). false = in-process memory only
set REDIS_ENABLED=true
set REDIS_HOST=127.0.0.1
set REDIS_PORT=6379
set REDIS_DB=0
