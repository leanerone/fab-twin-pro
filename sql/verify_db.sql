SET PAGESIZE 50
SET LINESIZE 200
SET FEEDBACK OFF

PROMPT === 平台表数量（不含DT表）===
SELECT COUNT(*) AS platform_tables FROM user_tables WHERE table_name NOT LIKE 'DT_%';

PROMPT === SEQUENCE 数量 ===
SELECT COUNT(*) AS sequences FROM user_sequences;

PROMPT === TRIGGER 数量 ===
SELECT COUNT(*) AS triggers FROM user_triggers WHERE trigger_name LIKE 'TRG_%_ID';

PROMPT === 机台数量 ===
SELECT COUNT(*) AS machines FROM machines;

PROMPT === 用户数量 ===
SELECT COUNT(*) AS users FROM users;

PROMPT === 角色数量 ===
SELECT COUNT(*) AS roles FROM roles;

PROMPT === 权限数量 ===
SELECT COUNT(*) AS permissions FROM perm_data;

PROMPT === 角色权限映射 ===
SELECT role_id, COUNT(*) AS perm_count FROM role_permissions GROUP BY role_id ORDER BY role_id;

EXIT;
