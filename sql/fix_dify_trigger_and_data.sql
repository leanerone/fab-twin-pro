-- ============================================================
-- FabTwin Pro — Dify 配置问题修复脚本 v2 (ver2.9.5-P批)
-- 日期: 2026-09-03
-- 用途: 重建 MACHINE_DIFY_CONFIGS 触发器 + 清理 "None" 脏数据
-- 运行环境: SQL Plus / SQL Developer，连接 emuuser@APCDB
-- 注意: CONFIG_VALUE 是 CLOB 类型，必须用 DBMS_LOB 包操作
-- ============================================================

-- ============================================================
-- 1. 重建触发器 TRG_MACHINE_DIFY_CONFIGS_ID (强制重建，解决 INVALID)
-- ============================================================

CREATE OR REPLACE TRIGGER TRG_MACHINE_DIFY_CONFIGS_ID
BEFORE INSERT ON MACHINE_DIFY_CONFIGS
FOR EACH ROW
BEGIN
    IF :NEW.ID IS NULL THEN
        SELECT SEQ_MACHINE_DIFY_CONFIGS.NEXTVAL INTO :NEW.ID FROM DUAL;
    END IF;
END;
/

-- ============================================================
-- 2. 清理 AI_CONFIGS 中的字符串 "None" 脏数据
--    CLOB 字段必须用 DBMS_LOB 操作，不能直接用 =
-- ============================================================

UPDATE AI_CONFIGS
SET CONFIG_VALUE = EMPTY_CLOB(),
    UPDATED_AT = TO_CHAR(SYSTIMESTAMP AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
    UPDATED_BY = 'cleanup'
WHERE DBMS_LOB.SUBSTR(CONFIG_VALUE, 4000, 1) = 'None'
   OR (CONFIG_VALUE IS NULL)
   OR (DBMS_LOB.GETLENGTH(CONFIG_VALUE) = 0 AND CONFIG_VALUE IS NOT NULL);

COMMIT;


-- ============================================================
-- 3. 验证触发器状态（应该都是 ENABLED + VALID）
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
-- 4. 验证 AI_CONFIGS 数据（用 DBMS_LOB.SUBSTR 处理 CLOB）
-- ============================================================

SELECT CONFIG_KEY,
       CASE
         WHEN CONFIG_VALUE IS NULL THEN '(NULL)'
         WHEN DBMS_LOB.GETLENGTH(CONFIG_VALUE) = 0 THEN '(空)'
         WHEN CONFIG_KEY LIKE '%api_key%'
           OR CONFIG_KEY LIKE '%secret%'
           OR CONFIG_KEY LIKE '%token%'
         THEN DBMS_LOB.SUBSTR(CONFIG_VALUE, 8, 1) || '****'
         ELSE DBMS_LOB.SUBSTR(CONFIG_VALUE, 50, 1)
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
