SET LINESIZE 200
SET PAGESIZE 100
COL username FORMAT A30
COL account_status FORMAT A20
SELECT username, account_status FROM dba_users WHERE username IN ('FABTWIN','SYSTEM','SYS');
EXIT
