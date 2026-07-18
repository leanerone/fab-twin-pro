set ORACLE_HOME=N:\WINDOWS.X64_193000_db_home
set PATH=%ORACLE_HOME%\BIN;%PATH%
set ORACLE_SID=ORCL
echo connect / as sysdba; > temp_check.sql
echo SELECT name, open_mode FROM v$pdbs; >> temp_check.sql
echo exit; >> temp_check.sql
sqlplus /nolog @temp_check.sql
