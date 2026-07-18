set ORACLE_HOME=N:\WINDOWS.X64_193000_db_home
set PATH=%ORACLE_HOME%\BIN;%PATH%
set ORACLE_SID=ORCL

(
echo connect / as sysdba;
echo ALTER SESSION SET CONTAINER=ORCLPDB;
echo CREATE TABLESPACE fabtwin_data DATAFILE 'fabtwin_data01.dbf' SIZE 500M AUTOEXTEND ON NEXT 100M MAXSIZE 2G;
echo CREATE TEMPORARY TABLESPACE fabtwin_temp TEMPFILE 'fabtwin_temp01.dbf' SIZE 100M AUTOEXTEND ON NEXT 50M MAXSIZE 500M;
echo CREATE USER fabtwin IDENTIFIED BY fabtwin DEFAULT TABLESPACE fabtwin_data TEMPORARY TABLESPACE fabtwin_temp;
echo GRANT CONNECT, RESOURCE, DBA TO fabtwin;
echo GRANT UNLIMITED TABLESPACE TO fabtwin;
echo exit;
) > create_user.sql

sqlplus /nolog @create_user.sql
