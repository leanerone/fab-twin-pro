set ORACLE_HOME=N:\WINDOWS.X64_193000_db_home
set PATH=%ORACLE_HOME%\BIN;%PATH%
set ORACLE_SID=ORCL
echo SELECT table_name FROM user_tables ORDER BY table_name; > list_tables.sql
echo EXIT; >> list_tables.sql
sqlplus -S fabtwin/fabtwin@localhost:1521/ORCLPDB @list_tables.sql
