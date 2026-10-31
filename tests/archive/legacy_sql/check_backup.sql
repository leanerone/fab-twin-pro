SET LINESIZE 200
SET PAGESIZE 100

-- 1. 检查闪回区域
SELECT name, space_limit, space_used, space_reclaimable FROM v$recovery_file_dest;

-- 2. 检查 RMAN 备份
SELECT session_key, start_time, status, input_type FROM v$rman_backup_job_details ORDER BY start_time DESC FETCH FIRST 5 ROWS ONLY;

-- 3. 检查数据泵导出
SELECT owner, object_name, created FROM dba_directories WHERE directory_name LIKE '%DUMP%' OR directory_name LIKE '%EXP%' OR directory_name LIKE '%BACKUP%';

-- 4. 回收站（DROP USER CASCADE 不进回收站，但检查一下）
SELECT owner, original_name, droptime, type FROM dba_recyclebin WHERE owner='FABTWIN' ORDER BY droptime DESC FETCH FIRST 10 ROWS ONLY;

-- 5. 检查闪回版本（如果 SUPPLEMENTAL LOGGING 开了）
SELECT supplemental_log_data_min, supplemental_log_data_pk, supplemental_log_data_all FROM v$database;

-- 6. 最近的归档日志
SELECT sequence#, completion_time, name FROM v$archived_log WHERE completion_time > SYSDATE-7 ORDER BY completion_time DESC FETCH FIRST 5 ROWS ONLY;

EXIT;
