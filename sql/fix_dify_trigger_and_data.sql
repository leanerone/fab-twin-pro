-- ============================================================
-- FabTwin Pro — Dify 配置问题修复脚本 (ver2.9.5-P批)
-- 日期: 2026-09-03
-- 用途: 修复 MACHINE_DIFY_CONFIGS 触发器 INVALID + 清理 "None" 脏数据
-- 运行环境: SQL Plus / SQL Developer，连接 emuuser@APCDB
-- 运行方式: @fix_dify_trigger_and_data.sql
-- ============================================================

-- ============================================================
-- 1. 修复触发器 TRG_MACHINE_DIFY_CONFIGS_ID (INVALID → VALID)
-- ============================================================

-- 先尝试编译（如果只是编译失效，这一句就够了）
ALTER TRIGGER TRG_MACHINE_DIFY_CONFIGS_ID COMPILE;


-- 如果编译后还是 INVALID，用下面的 CREATE OR REPLACE 重建
-- （取消注释后执行）
-- CREATE OR REPLACE TRIGGER TRG_MACHINE_DIFY_CONFIGS_ID
-- BEFORE INSERT ON MACHINE_DIFY_CONFIGS
-- FOR EACH ROW
-- BEGIN
--     IF :NEW.ID IS NULL THEN
--         SELECT SEQ_MACHINE_DIFY_CONFIGS.NEXTVAL INTO :NEW.ID FROM DUAL;
--     END IF;
-- END;
-- /


-- ============================================================
-- 2. 清理 AI_CONFIGS 中的字符串 "None" 脏数据
--    之前 _save_to_db 把 Python None 存成了字符串 "None"
--    现在后端已修复（None→空字符串），这里清理历史脏数据
-- ============================================================

UPDATE AI_CONFIGS
SET CONFIG_VALUE = '',
    UPDATED_AT = TO_CHAR(SYSTIMESTAMP AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
    UPDATED_BY = 'cleanup'
WHERE CONFIG_VALUE = 'None'
   OR CONFIG_VALUE IS NULL;

COMMIT;


-- ============================================================
-- 3. 验证触发器状态（执行后看输出，应该都是 VALID）
-- ============================================================

SELECT t.TRIGGER_NAME,
       t.TABLE_NAME,
       t.STATUS        AS TRIGGER_STATUS,
       o.STATUS        AS OBJECT_STATUS
FROM USER_TRIGGERS t
LEFT JOIN USER_OBJECTS o
  ON o.OBJECT_NAME = t.TRIGGER_NAME
 AND o.OBJECT_TYPE = 'TRIGGER'
WHERE t.TRIGGER_NAME IN ('TRG_AI_CONFIGS_ID', 'TRG_MACHINE_DIFY_CONFIGS_ID')
ORDER BY t.TRIGGER_NAME;


-- ============================================================
-- 4. 验证 AI_CONFIGS 数据（确认 "None" 已清理）
-- ============================================================

SELECT CONFIG_KEY,
       CASE
         WHEN CONFIG_VALUE IS NULL THEN '(NULL)'
         WHEN DBMS_LOB.GETLENGTH(CONFIG_VALUE) = 0 THEN '(空)'
         WHEN CONFIG_KEY LIKE '%api_key%'
           OR CONFIG_KEY LIKE '%secret%'
           OR CONFIG_KEY LIKE '%token%'
         THEN SUBSTR(CONFIG_VALUE, 1, 8) || '****'
         ELSE SUBSTR(CONFIG_VALUE, 1, 50)
       END AS VALUE_PREVIEW,
       UPDATED_AT,
       UPDATED_BY
FROM AI_CONFIGS
WHERE CONFIG_KEY LIKE 'dify_%'
   OR CONFIG_KEY LIKE 'n8n_%'
   OR CONFIG_KEY LIKE 'mcp_n8n_%'
ORDER BY CONFIG_KEY;


-- ============================================================
-- 5. 完成
-- ============================================================
EXIT;
