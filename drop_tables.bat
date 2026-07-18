set ORACLE_HOME=N:\WINDOWS.X64_193000_db_home
set PATH=%ORACLE_HOME%\BIN;%PATH%
set ORACLE_SID=ORCL
echo Dropping all tables...
(
echo connect fabtwin/fabtwin@localhost:1521/ORCLPDB;
echo BEGIN
echo   FOR rec IN ^(SELECT table_name FROM user_tables^) LOOP
echo     EXECUTE IMMEDIATE 'DROP TABLE ' ^|^| rec.table_name ^|^| ' CASCADE CONSTRAINTS PURGE';
echo   END LOOP;
echo END;
echo /
echo exit;
) > drop_all_tables.sql
sqlplus -S /nolog @drop_all_tables.sql
echo Done!
