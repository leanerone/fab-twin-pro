@echo off
set ORACLE_HOME=N:\WINDOWS.X64_193000_db_home
set PATH=%ORACLE_HOME%\BIN;%PATH%
set ORACLE_SID=ORCL
cd /d %~dp0
echo Starting database initialization...
sqlplus -S fabtwin/fabtwin@localhost:1521/ORCLPDB @sql\init_oracle_db.sql > init_db.log 2>&1
echo Done. Check init_db.log for details.
