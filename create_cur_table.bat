set ORACLE_HOME=N:\WINDOWS.X64_193000_db_home
set PATH=%ORACLE_HOME%\BIN;%PATH%
set ORACLE_SID=ORCL

echo Creating DT_EVENT_RAW_CUR table...
(
echo connect fabtwin/fabtwin@localhost:1521/ORCLPDB;
echo CREATE TABLE DT_EVENT_RAW_CUR ^(
echo     tool_id VARCHAR2^(255^) PRIMARY KEY,
echo     raw_id VARCHAR2^(255^),
echo     source_system VARCHAR2^(255^) NOT NULL,
echo     source_message_id VARCHAR2^(255^) NOT NULL,
echo     received_ts_utc VARCHAR2^(255^),
echo     event_ts_utc VARCHAR2^(255^),
echo     payload_json CLOB,
echo     parse_status VARCHAR2^(255^) DEFAULT 'NEW',
echo     error_message VARCHAR2^(255^)
echo ^);
echo exit;
) > create_cur_table.sql

sqlplus -S /nolog @create_cur_table.sql
echo Done!
